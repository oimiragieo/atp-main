
use serde::Serialize;
use atp_adapter_proto::atp::adapter::v1::{adapter_service_client::AdapterServiceClient, HealthRequest};
#[derive(Serialize)]
pub struct AdapterHealth { pub endpoint: String, pub ok: bool, pub p95_ms: f64, pub error_rate: f64 }

pub async fn check_endpoints(eps: Vec<String>) -> Vec<AdapterHealth> {
    let mut out = vec![];
    for ep in eps {
        let mut ok = false; let mut p95 = 0.0; let mut er = 0.0;
        if let Ok(mut cli) = AdapterServiceClient::connect(ep.clone()).await {
            if let Ok(resp) = cli.health(tonic::Request::new(HealthRequest{})).await {
                let h = resp.into_inner();
                ok = true; p95 = h.p95_ms; er = h.error_rate;
            }
        }
        out.push(AdapterHealth{ endpoint: ep, ok, p95_ms: p95, error_rate: er });
    }
    out
}
