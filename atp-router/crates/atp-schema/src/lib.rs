use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

/// Default maximum bytes of text per fragment when no explicit policy is provided.
pub const DEFAULT_MAX_FRAGMENT_BYTES: usize = 8 * 1024; // 8 KiB

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Window { pub max_parallel: u32, pub max_tokens: u64, pub max_usd_micros: u64 }
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostEst { pub in_tokens: u64, pub out_tokens: u64, pub usd_micros: u64 }
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Meta {
    pub task_type: Option<String>,
    pub languages: Option<Vec<String>>,
    pub risk: Option<String>,
    pub data_scope: Option<Vec<String>>,
    pub trace: Option<serde_json::Value>,
    pub tool_permissions: Option<Vec<String>>,
    pub environment_id: Option<String>,
    pub security_groups: Option<Vec<String>>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Payload {
    pub r#type: String,
    pub content: serde_json::Value,
    pub confidence: Option<f32>,
    pub cost_est: Option<CostEst>,
    pub checksum: Option<String>,
    pub expiry_ms: Option<u64>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Frame {
    pub v: u8,
    pub session_id: String,
    pub stream_id: String,
    pub msg_seq: u64,
    pub frag_seq: u32,
    pub flags: Vec<String>,
    pub qos: String,
    pub ttl: u8,
    pub window: Window,
    pub meta: Meta,
    pub payload: Payload,
    pub sig: Option<String>,
    pub checksum: Option<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding { pub id: String, pub severity: Option<String>, pub claim: String, pub confidence: Option<f32>, pub provenance: Option<Vec<String>> }

pub fn fragment_text_frame(base: Frame, text: &str, max_fragment_bytes: usize) -> Vec<Frame> {
    if text.len() <= max_fragment_bytes { let mut f = base; f.flags.retain(|fl| fl != "MORE"); return vec![f.with_computed_checksum().expect("checksum")]; }
    let bytes = text.as_bytes();
    let total_chunks = (bytes.len() + max_fragment_bytes - 1) / max_fragment_bytes;
    let mut out = Vec::with_capacity(total_chunks);
    for (i, chunk) in bytes.chunks(max_fragment_bytes).enumerate() {
        let mut f = base.clone();
        f.frag_seq = i as u32;
        f.payload.content = serde_json::json!({"text": String::from_utf8_lossy(chunk)});
        if i < total_chunks - 1 { if !f.flags.iter().any(|x| x=="MORE") { f.flags.push("MORE".into()); } } else { f.flags.retain(|fl| fl != "MORE"); }
        out.push(f.with_computed_checksum().expect("checksum"));
    }
    out
}

pub fn reassemble_text(frames: &[Frame]) -> Option<String> {
    if frames.is_empty() { return None; }
    for (idx, f) in frames.iter().enumerate() {
        if f.frag_seq != idx as u32 { return None; }
        if idx < frames.len()-1 && !f.flags.iter().any(|x| x=="MORE") { return None; }
        if idx == frames.len()-1 && f.flags.iter().any(|x| x=="MORE") { return None; }
    }
    let mut buf = String::new();
    for f in frames { if let Some(obj) = f.payload.content.as_object() { if let Some(v) = obj.get("text") { if let Some(s) = v.as_str() { buf.push_str(s); } } } }
    Some(buf)
}

#[derive(Default, Debug)]
pub struct Reassembler { expected_next: u32, buffer: Vec<Frame>, complete: bool }
impl Reassembler {
    pub fn push(&mut self, frame: Frame) -> Option<Vec<Frame>> {
        if self.complete { return None; }
        if frame.frag_seq != self.expected_next { return None; }
        self.expected_next += 1;
        let is_last = !frame.flags.iter().any(|f| f=="MORE");
        self.buffer.push(frame);
        if is_last { self.complete = true; return Some(std::mem::take(&mut self.buffer)); }
        None
    }
}

impl Frame {
    pub fn compute_checksum(&self) -> Result<String, serde_json::Error> {
        let mut value = serde_json::to_value(self)?;
        if let Some(obj) = value.as_object_mut() { obj.remove("checksum"); obj.remove("sig"); }
        let canonical = serde_json::to_vec(&value)?;
        let mut hasher = Sha256::new(); hasher.update(canonical); Ok(format!("{:x}", hasher.finalize()))
    }
    pub fn with_computed_checksum(mut self) -> Result<Self, serde_json::Error> { let c = self.compute_checksum()?; self.checksum = Some(c); Ok(self) }
    pub fn verify_checksum(&self) -> bool { match (self.checksum.as_ref(), self.compute_checksum()) { (Some(existing), Ok(recalc)) => existing == &recalc, _ => false } }
}

pub fn validate_fragment_checksums(frames: &[Frame]) -> bool { frames.iter().all(|f| f.verify_checksum()) }

#[cfg(test)]
mod tests { use super::*; use proptest::prelude::*;
    fn sample_frame() -> Frame { Frame { v:1, session_id:"sess1".into(), stream_id:"streamA".into(), msg_seq:42, frag_seq:0, flags: vec!["MORE".into()], qos:"gold".into(), ttl:5, window: Window{ max_parallel:4, max_tokens:10_000, max_usd_micros:2_000_000 }, meta: Meta{ task_type:Some("ask".into()), languages:None, risk:None, data_scope:None, trace:None, tool_permissions:None, environment_id:None, security_groups:None }, payload: Payload{ r#type:"text".into(), content: serde_json::json!({"text":"hello"}), confidence:Some(0.9), cost_est:None, checksum:None, expiry_ms:None }, sig:None, checksum:None } }
    proptest! { #[test] fn prop_round_trip_random(msg_seq in 0u64..1_000_000, frag_seq in 0u32..1000, qos in prop_oneof![Just("gold".to_string()), Just("silver".to_string()), Just("bronze".to_string())], text in "[a-zA-Z0-9 ]{0,64}") { let frame = Frame { v:1, session_id:"sessX".into(), stream_id:"streamY".into(), msg_seq, frag_seq, flags: vec!["MORE".into()], qos: qos.clone(), ttl:5, window: Window{ max_parallel:8, max_tokens:50_000, max_usd_micros:5_000_000 }, meta: Meta{ task_type:Some("ask".into()), languages:None, risk:None, data_scope:None, trace:None, tool_permissions:None, environment_id:None, security_groups:None }, payload: Payload{ r#type:"text".into(), content: serde_json::json!({"text":text}), confidence:None, cost_est:None, checksum:None, expiry_ms:None }, sig:None, checksum:None }.with_computed_checksum().unwrap(); let json = serde_json::to_string(&frame).unwrap(); let back: Frame = serde_json::from_str(&json).unwrap(); prop_assert_eq!(frame.msg_seq, back.msg_seq); prop_assert_eq!(frame.frag_seq, back.frag_seq); let back_checksum_clone = back.checksum.clone(); prop_assert_eq!(frame.checksum, back_checksum_clone); let c2 = back.compute_checksum().unwrap(); prop_assert_eq!(back.checksum.unwrap(), c2); } }
    #[test] fn round_trip_serialization() { let frame = sample_frame().with_computed_checksum().unwrap(); let json = serde_json::to_string(&frame).unwrap(); let de: Frame = serde_json::from_str(&json).unwrap(); assert_eq!(de.msg_seq, frame.msg_seq); assert_eq!(de.checksum, frame.checksum); }
    #[test] fn checksum_changes_on_mutation() { let mut frame = sample_frame().with_computed_checksum().unwrap(); let orig = frame.checksum.clone(); frame.payload.content = serde_json::json!({"text":"hello world"}); let new_sum = frame.compute_checksum().unwrap(); assert_ne!(orig.unwrap(), new_sum); }
    #[test] fn invalid_frame_missing_required_field() { let mut value = serde_json::to_value(sample_frame()).unwrap(); if let Some(obj) = value.as_object_mut() { obj.remove("session_id"); } let json = serde_json::to_string(&value).unwrap(); let de: Result<Frame, _> = serde_json::from_str(&json); assert!(de.is_err(), "Deserialization should fail without session_id"); }
    #[test] fn fragmentation_and_reassembly() { let base = sample_frame(); let text = "a".repeat(2050); let frags = fragment_text_frame(base, &text, 800); assert!(frags.len() >= 3); for (i,f) in frags.iter().enumerate() { if i < frags.len()-1 { assert!(f.flags.iter().any(|x| x=="MORE")); } else { assert!(!f.flags.iter().any(|x| x=="MORE")); } } let mut r = Reassembler::default(); let mut collected = Vec::new(); for f in frags.clone() { if let Some(done) = r.push(f) { collected = done; } } assert!(!collected.is_empty()); let re_text = reassemble_text(&collected).expect("reassembled"); assert_eq!(re_text, text); assert!(validate_fragment_checksums(&collected)); let mut r2 = Reassembler::default(); let mut out_none = 0; let mut rev = frags.clone(); rev.reverse(); for f in rev { if r2.push(f).is_none() { out_none += 1; } } assert!(out_none > 0); }
    #[test] fn fragmentation_missing_last_never_completes() { let base = sample_frame(); let text = "b".repeat(1500); let mut frags = fragment_text_frame(base, &text, 600); assert!(frags.len() > 2); frags.pop(); let mut r = Reassembler::default(); for f in frags { assert!(r.push(f).is_none()); } }
    #[test] fn fragmentation_mid_fragment_missing_more_flag_detected() { let base = sample_frame(); let text = "c".repeat(1700); let mut frags = fragment_text_frame(base, &text, 500); assert!(frags.len() >= 3); if frags.len() > 2 { frags[1].flags.retain(|x| x!="MORE"); } assert!(reassemble_text(&frags).is_none()); }
}
