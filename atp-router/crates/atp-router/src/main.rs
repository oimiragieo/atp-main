
use axum::{routing::{get}, Router, extract::{Query, ws::{WebSocketUpgrade, WebSocket, Message}}};
use std::collections::{HashMap, VecDeque};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};
use futures_util::{StreamExt, SinkExt};
use serde_json::json;
use std::time::Duration;
use axum::response::Response;
use atp_schema::{Frame, Window, Meta};
use tokio::time::{Instant};
use tokio::sync::{mpsc, RwLock};
use metrics::{counter, histogram, gauge};
use metrics_exporter_prometheus::PrometheusBuilder;
use once_cell::sync::Lazy;
use tracing::Instrument;

mod adapters;
mod consensus;

#[derive(Default)]
struct WindowState { inflight: u32, tokens: u64, usd: u64, last_backpressure: Option<Instant> }
type SessionKey = String;
#[derive(Default)]
struct WindowTable { inner: RwLock<HashMap<SessionKey, WindowState>> }
impl WindowTable {
    async fn admit(&self, key: &str, w: &Window, est_tokens: u64, est_usd: u64) -> bool {
        let mut map = self.inner.write().await;
        let e = map.entry(key.to_string()).or_default();
        if e.inflight >= w.max_parallel { return false; }
        if e.tokens + est_tokens > w.max_tokens { return false; }
        if e.usd + est_usd > w.max_usd_micros { return false; }
        e.inflight += 1; e.tokens += est_tokens; e.usd += est_usd; true
    }
    async fn ack(&self, key: &str, est_tokens: u64, est_usd: u64) {
        let mut map = self.inner.write().await;
        if let Some(e) = map.get_mut(key) {
            e.inflight = e.inflight.saturating_sub(1);
            e.tokens = e.tokens.saturating_sub(est_tokens);
            e.usd = e.usd.saturating_sub(est_usd);
        }
    }
    async fn mark_backpressure(&self, key: &str) {
        let mut map = self.inner.write().await;
        if let Some(e) = map.get_mut(key) { e.last_backpressure = Some(Instant::now()); }
    }
    async fn under_pressure(&self, key: &str) -> bool {
        let map = self.inner.read().await;
        map.get(key).and_then(|e| e.last_backpressure).map(|t| t.elapsed() < Duration::from_secs(2)).unwrap_or(false)
    }
}
static GLOBAL_WINDOWS: Lazy<WindowTable> = Lazy::new(|| WindowTable { inner: RwLock::new(HashMap::new()) });

#[derive(Clone, Debug)]
enum Lane { Gold, Silver, Bronze }
fn lane_from_qos(q: &str) -> Lane {
    match q.to_lowercase().as_str() {
        "gold" => Lane::Gold,
        "silver" => Lane::Silver,
        _ => Lane::Bronze,
    }
}
#[derive(Clone)]
struct WorkItem { frame: Frame, reply_tx: mpsc::Sender<String> }
struct Scheduler { gold: mpsc::Sender<WorkItem>, silver: mpsc::Sender<WorkItem>, bronze: mpsc::Sender<WorkItem> }
static SCHED: Lazy<Scheduler> = Lazy::new(|| {
    let (g_tx, mut g_rx) = mpsc::channel::<WorkItem>(256);
    let (s_tx, mut s_rx) = mpsc::channel::<WorkItem>(256);
    let (b_tx, mut b_rx) = mpsc::channel::<WorkItem>(256);
    tokio::spawn(async move {
        let mut order = VecDeque::from(vec![Lane::Gold, Lane::Gold, Lane::Gold, Lane::Gold, Lane::Gold,
                                            Lane::Silver, Lane::Silver, Lane::Silver,
                                            Lane::Bronze]);
        loop {
            if let Some(l) = order.pop_front() {
                order.push_back(l.clone());
                let item_opt = match l {
                    Lane::Gold => g_rx.recv().await,
                    Lane::Silver => s_rx.recv().await,
                    Lane::Bronze => b_rx.recv().await,
                };
                if let Some(item) = item_opt {
                    tokio::spawn(process_request(item).instrument(tracing::info_span!("dispatch")));
                } else {
                    tokio::time::sleep(Duration::from_millis(5)).await;
                }
            }
        }
    });
    Scheduler { gold: g_tx, silver: s_tx, bronze: b_tx }
});

async fn metrics_handler()->String{ static PROM: Lazy<metrics_exporter_prometheus::PrometheusHandle> = Lazy::new(|| PrometheusBuilder::new().install_recorder().expect("install")); PROM.render() }
async fn explain_route()->String{ "[]".into() }
async fn ws_handler(ws: WebSocketUpgrade) -> Response { ws.on_upgrade(handle_socket) }

fn opa_allow(meta: &Meta) -> bool {
    if let Ok(url) = std::env::var("OPA_URL") {
        let client = reqwest::blocking::Client::new();
        let input = json!({"meta": meta});
        let endpoint = format!("{}/v1/data/atp/policy/allow", url.trim_end_matches('/'));
        if let Ok(resp) = client.post(endpoint).json(&json!({"input":input})).send() {
            if let Ok(v) = resp.json::<serde_json::Value>() {
                return v.get("result").and_then(|r| r.as_bool()).unwrap_or(true);
            }
        }
        true
    } else { true }
}

async fn estimate_costs(endpoints: &Vec<String>, prompt_json: &str) -> (u64, u64) {
    use atp_adapter_proto::atp::adapter::v1::{adapter_service_client::AdapterServiceClient, EstimateRequest};
    let mut tasks = vec![];
    for ep in endpoints.iter() {
        let epc = ep.clone();
        let p = prompt_json.to_string();
        tasks.push(tokio::spawn(async move {
            match AdapterServiceClient::connect(epc.clone()).await {
                Ok(mut cli) => {
                    let req = tonic::Request::new(EstimateRequest{ stream_id: "s".into(), task_type: "generic".into(), prompt_json: p });
                    match cli.estimate(req).await {
                        Ok(r) => { let e = r.into_inner(); Ok::<(u64,u64),String>((e.in_tokens + e.out_tokens, e.usd_micros)) }
                        Err(e) => Err(format!("estimate rpc: {}", e))
                    }
                }
                Err(e) => Err(format!("connect: {}", e))
            }
        }));
    }
    let mut toks=0u64; let mut usd=0u64;
    for t in tasks {
        if let Ok(res) = t.await { if let Ok((tk,us)) = res { toks += tk; usd += us; } }
    }
    (toks, usd)
}

async fn process_request(item: WorkItem) {
    let span = tracing::info_span!(
        "process_request",
        stream_id = %item.frame.stream_id,
        session_id = %item.frame.session_id,
        msg_seq = item.frame.msg_seq,
        frag_seq = item.frame.frag_seq,
        qos = %item.frame.qos
    );
    let _e = span.enter();
    let mut frame = item.frame;
    if !opa_allow(&frame.meta) { let _ = item.reply_tx.send(json!({"error":"policy_denied"}).to_string()).await; return; }
    let endpoints: Vec<String> = std::env::var("ADAPTER_ENDPOINTS").ok().and_then(|s| serde_json::from_str(&s).ok()).unwrap_or(vec!["http://persona_adapter:7070".into(), "http://ollama_adapter:7070".into()]);
    let prompt_json = frame.payload.content.to_string();
    let (need_tokens, need_usd) = estimate_costs(&endpoints, &prompt_json).await;
    histogram!("router_estimate_tokens", need_tokens as f64);
    histogram!("router_estimate_usd_micros", need_usd as f64);

    let key = format!("{}:{}", frame.session_id, frame.stream_id);
    if !GLOBAL_WINDOWS.admit(&key, &frame.window, need_tokens, need_usd).await {
        let _ = item.reply_tx.send(json!({"control.status":"BUSY","suggested_wait_ms":200}).to_string()).await;
        GLOBAL_WINDOWS.mark_backpressure(&key).await;
        counter!("router_windows_reject_total", 1);
        return;
    }
    if GLOBAL_WINDOWS.under_pressure(&key).await {
        if frame.qos.to_lowercase()=="bronze" {
            counter!("router_qos_drops_bronze_total", 1);
            let _ = item.reply_tx.send(json!({"control.status":"ECN","action":"drop","reason":"pressure"}).to_string()).await;
            GLOBAL_WINDOWS.ack(&key, need_tokens, need_usd).await;
            return;
        }
    }
    counter!("router_windows_admit_total", 1);
    let ack = json!({
        "v": frame.v, "session_id": frame.session_id, "stream_id": frame.stream_id,
        "msg_seq": frame.msg_seq, "frag_seq": frame.frag_seq, "flags":["ACK"], "qos": frame.qos,
        "ttl": frame.ttl-1, "window": frame.window, "meta": frame.meta,
        "payload": {"type":"agent.result.partial","content":{"router":"ack"}},
    });
    let ack_json = ack.to_string();
    counter!("frames_tx_total", 1, "kind"=>"ack", "qos"=>frame.qos.clone());
    let _ = item.reply_tx.send(ack_json).await;

    // per-ep predictions
    use atp_adapter_proto::atp::adapter::v1::{adapter_service_client::AdapterServiceClient as _AdapterCli, EstimateRequest as _EstimateReq};
    let mut per_ep_pred: HashMap<String,(u64,u64)> = HashMap::new();
    for ep in endpoints.iter() {
        if let Ok(mut c) = _AdapterCli::connect(ep.clone()).await {
            if let Ok(r) = c.estimate(tonic::Request::new(_EstimateReq{ stream_id: "s".into(), task_type: "generic".into(), prompt_json: prompt_json.clone() })).await {
                let e = r.into_inner();
                per_ep_pred.insert(ep.clone(), (e.in_tokens + e.out_tokens, e.usd_micros));
            }
        }
    }

    use atp_adapter_proto::atp::adapter::v1::{adapter_service_client::AdapterServiceClient, StreamRequest};
    let (tx, mut rx) = mpsc::channel::<serde_json::Value>(64);
    let mut join_handles = vec![];
    let req_span = tracing::info_span!("fanout", adapters = endpoints.len());
    let _s = req_span.enter();

    for ep in endpoints.clone() {
        let txc = tx.clone();
        let prompt = prompt_json.clone();
        let v = frame.v; let sid = frame.session_id.clone(); let st = frame.stream_id.clone();
        let msg_seq = frame.msg_seq; let frag_seq = frame.frag_seq; let qos = frame.qos.clone();
        let ttl = frame.ttl-1; let w = frame.window.clone(); let m = frame.meta.clone();
        join_handles.push(tokio::spawn(async move {
            let span = tracing::info_span!("adapter_stream", adapter = %ep);
            let _e = span.enter();
            let mut observed_tokens: u64 = 0; let mut observed_usd: u64 = 0;
            let mut cli = match AdapterServiceClient::connect(ep.clone()).await {
                Ok(c) => c,
                Err(e) => { let _ = txc.send(json!({"error":"connect","adapter":ep,"reason":e.to_string()})).await; return; }
            };
            let req = tonic::Request::new(StreamRequest{ stream_id: "s".into(), prompt_json: prompt });
            match cli.stream(req).await {
                Ok(mut stream) => {
                    use tokio_stream::StreamExt;
                    while let Ok(Some(res)) = stream.get_mut().message().await {
                        // Handle the stream chunk directly
                        observed_tokens += (res.partial_in_tokens + res.partial_out_tokens) as u64;
                        observed_usd += res.partial_usd_micros as u64;
                        let out = json!({
                            "v": v, "session_id": sid, "stream_id": st,
                            "msg_seq": msg_seq+1, "frag_seq": frag_seq, "flags":["MORE"],
                            "qos": qos, "ttl": ttl, "window": w, "meta": m,
                            "payload": {"type": res.r#type, "content": res.content_json, "confidence": res.confidence},
                            "adapter": ep,
                        });
                        counter!("frames_tx_total", 1, "kind"=>"partial", "adapter"=>ep.clone());
                        let _ = txc.send(out).await;
                    }
                }
                Err(e) => { let _ = txc.send(json!({"error":"rpc","adapter":ep,"reason":e.to_string()})).await; }
            }
            let _ = txc.send(json!({ "type":"stats","adapter":ep, "observed_tokens": observed_tokens, "observed_usd": observed_usd })).await;
        }));
    }
    drop(tx);

    let mut finals: Vec<String> = vec![];
    let mut provisional_sent = false;
    let mut provisional_conf: f32 = 0.0;
    let start_t = Instant::now();

    while let Some(msgv) = rx.recv().await {
        if let Some(_err) = msgv.get("error") {
            let _ = item.reply_tx.send(json!({"payload":{"type":"agent.result.partial","content":{"adapter_error":msgv}}}).to_string()).await;
            continue;
        }
        if msgv.get("type").and_then(|x| x.as_str()) == Some("stats") {
            if let (Some(adapter), Some(obs_t), Some(obs_u)) = (
                msgv.get("adapter").and_then(|x| x.as_str()),
                msgv.get("observed_tokens").and_then(|x| x.as_u64()),
                msgv.get("observed_usd").and_then(|x| x.as_u64()),
            ) {
                if let Some((pred_t, pred_u)) = per_ep_pred.get(adapter).cloned() {
                    let mape_t = if pred_t>0 { (obs_t as f64 - pred_t as f64).abs() / pred_t as f64 } else { 0.0 };
                    let mape_u = if pred_u>0 { (obs_u as f64 - pred_u as f64).abs() / pred_u as f64 } else { 0.0 };
                    histogram!("router_estimate_mape_tokens", mape_t);
                    histogram!("router_estimate_mape_usd", mape_u);
                    if obs_t > pred_t { counter!("router_estimate_under_rate_tokens_total", 1); }
                    if obs_u > pred_u { counter!("router_estimate_under_rate_usd_total", 1); }
                    histogram!("adapter_estimate_mape_tokens", mape_t, "adapter" => adapter.to_string());
                    histogram!("adapter_estimate_mape_usd", mape_u, "adapter" => adapter.to_string());
                }
            }
            continue;
        }

        let _ = item.reply_tx.send(msgv.to_string()).await;

        if let Some(payload) = msgv.get("payload") {
            if payload.get("type").and_then(|t| t.as_str()).unwrap_or("").ends_with("final") {
                if let Some(c) = payload.get("content") { finals.push(c.to_string()); }
                if !provisional_sent && finals.len() >= 2 {
                    let pcs = consensus::compute(&finals);
                    let top = pcs.scores.iter().cloned().fold(0.0, f32::max);
                    if top >= 0.66 || start_t.elapsed() > Duration::from_millis(700) {
                        let provisional = json!({
                            "v": frame.v, "session_id": frame.session_id, "stream_id": frame.stream_id,
                            "msg_seq": frame.msg_seq+1, "frag_seq": frame.frag_seq, "flags":["MORE"],
                            "qos": frame.qos, "ttl": frame.ttl-1, "window": frame.window, "meta": frame.meta,
                            "payload": {"type":"agent.result.provisional","content": {
                                "finals": pcs.finals, "groups": pcs.groups, "scores": pcs.scores
                            }, "expiry_ms": 1500}
                        });
                        let prov_json = provisional.to_string();
                        counter!("frames_tx_total", 1, "kind"=>"provisional");
                        let _ = item.reply_tx.send(prov_json).await;
                        provisional_sent = true; provisional_conf = top;
                        gauge!("router_consensus_confidence", top as f64);
                    }
                }
            }
        }
    }
    for j in join_handles { let _ = j.await; }

    let span = tracing::info_span!("consensus_final");
    let _e2 = span.enter();
    let cs = consensus::compute(&finals);
    if let Some(top) = cs.scores.iter().cloned().reduce(f32::max) {
        gauge!("router_consensus_confidence", top as f64);
        if provisional_sent && top + 0.05 < provisional_conf {
        let ctrl = json!({ "payload": {"type":"control.status","content":{"provisional":"DOWNGRADED","from":provisional_conf,"to":top}} });
        counter!("frames_tx_total", 1, "kind"=>"control");
        let _ = item.reply_tx.send(ctrl.to_string()).await;
        }
    }
    let final_msg = json!({
        "v": frame.v, "session_id": frame.session_id, "stream_id": frame.stream_id,
        "msg_seq": frame.msg_seq+2, "frag_seq": frame.frag_seq, "flags":["FIN"],
        "qos": frame.qos, "ttl": frame.ttl-1, "window": frame.window, "meta": frame.meta,
        "payload": {"type":"agent.result.final","content": {
            "finals": cs.finals, "representatives": cs.representatives, "groups": cs.groups, "scores": cs.scores
        }}
    });
    counter!("frames_tx_total", 1, "kind"=>"final");
    let _ = item.reply_tx.send(final_msg.to_string()).await;
    GLOBAL_WINDOWS.ack(&key, need_tokens, need_usd).await;
}

async fn adapters_health() -> String {
    let eps = std::env::var("ADAPTER_ENDPOINTS").ok()
        .and_then(|s| serde_json::from_str::<Vec<String>>(&s).ok())
        .unwrap_or_else(|| vec!["http://persona_adapter:7070".into(), "http://ollama_adapter:7070".into()]);
    let results = adapters::check_endpoints(eps).await;
    serde_json::to_string(&results).unwrap_or("[]".into())
}

async fn mem_put(Query(params): Query<HashMap<String, String>>) -> String {
    let enabled = std::env::var("FEATURE_WIRE_MEMORY").ok().as_deref() == Some("true");
    let ns = params.get("ns").cloned().unwrap_or_else(|| "tenant/acme".into());
    let key = params.get("key").cloned().unwrap_or_else(|| "demo".into());
    if enabled {
        let url = std::env::var("MEMORY_GATEWAY_URL").unwrap_or_else(|_| "http://memory-gateway:8080".into());
        let url = format!("{}/v1/memory/{}/{}", url.trim_end_matches('/'), ns, key);
        let body = serde_json::json!({"object":{"type":"demo","note":"hello from router"}});
        match reqwest::Client::new().put(url).json(&body).send().await {
            Ok(resp) => return format!("ok: {}", resp.status()),
            Err(e) => return format!("error: {}", e),
        }
    }
    "memory wiring disabled".into()
}

async fn handle_socket(socket: WebSocket) {
    let span = tracing::info_span!("ws_session");
    let _e = span.enter();
    let (out_tx, mut out_rx) = mpsc::channel::<String>(128);
    let (mut sender, mut receiver) = socket.split();
    tokio::spawn(async move {
        while let Some(line) = out_rx.recv().await { let _ = sender.send(Message::Text(line)).await; }
    });
    while let Some(msg) = receiver.next().await {
        match msg {
            Ok(Message::Text(txt)) => {
                let parse: Result<Frame, _> = serde_json::from_str(&txt);
                if parse.is_err() { let _ = out_tx.send(json!({"error":"invalid_frame"}).to_string()).await; continue; }
                let frame = parse.unwrap();
                counter!("frames_rx_total", 1, "qos"=>frame.qos.clone());
                tracing::debug!(
                    session_id=%frame.session_id,
                    stream_id=%frame.stream_id,
                    msg_seq=frame.msg_seq,
                    frag_seq=frame.frag_seq,
                    qos=%frame.qos,
                    ?frame.flags,
                    "frame_rx"
                );
                if frame.ttl == 0 { let _ = out_tx.send(json!({"error":"ttl_expired"}).to_string()).await; continue; }
                let item = WorkItem{ frame: frame.clone(), reply_tx: out_tx.clone() };
                let lane = lane_from_qos(&frame.qos);
                match lane {
                    Lane::Gold => { let _ = SCHED.gold.send(item).await; }
                    Lane::Silver => { let _ = SCHED.silver.send(item).await; }
                    Lane::Bronze => { let _ = SCHED.bronze.send(item).await; }
                }
            }
            Ok(Message::Binary(_)) => { let _ = out_tx.send(r#"{"error":"binary_not_supported"}"#.into()).await; }
            Ok(Message::Close(_)) | Err(_) => break,
            _ => {}
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {    let env_filter=std::env::var("RUST_LOG").unwrap_or_else(|_|"info,atp_router=debug".into());
    tracing_subscriber::registry()
        .with(tracing_subscriber::fmt::layer())
        .with(tracing_subscriber::EnvFilter::new(env_filter))
        .init();
    if let Ok(otlp) = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT") {
        // Simplified OpenTelemetry setup to avoid version conflicts
        tracing::info!("OpenTelemetry OTLP endpoint configured: {}", otlp);
    }

    let app=Router::new()
        .route("/healthz",get(||async{"ok"}))
        .route("/metrics",get(metrics_handler))
        .route("/ws",get(ws_handler))
        .route("/agp/explain",get(explain_route))
        .route("/adapters/health", get(adapters_health))
        .route("/mem/put", get(mem_put));

    let addr=std::net::SocketAddr::from(([0,0,0,0],7443));
    tracing::info!(%addr,"router listening");
    axum::serve(tokio::net::TcpListener::bind(addr).await?,app).await?; Ok(())
}
