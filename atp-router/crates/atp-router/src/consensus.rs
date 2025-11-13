
fn normalize(s: &str) -> String { s.to_lowercase().replace(|c: char| !c.is_alphanumeric() && c!=' ', " ") }
fn embed(s: &str, dim: usize) -> Vec<f32> {
    let mut v = vec![0f32; dim];
    for token in normalize(s).split_whitespace() {
        let mut x: u64 = 1469598103934665603;
        for b in token.as_bytes() { x ^= *b as u64; x = x.wrapping_mul(1099511628211); }
        let idx = (x % dim as u64) as usize;
        v[idx] += 1.0;
    }
    let n = (v.iter().map(|x| x*x).sum::<f32>()).sqrt().max(1e-6);
    for x in &mut v { *x /= n; }
    v
}
fn cosine(a: &[f32], b: &[f32]) -> f32 { a.iter().zip(b).map(|(x,y)| x*y).sum() }

pub struct ConsensusResult {
    pub finals: Vec<String>,
    pub representatives: Vec<(usize, String)>,
    pub groups: Vec<Vec<usize>>,
    pub scores: Vec<f32>,
}
pub fn compute(finals_json: &[String]) -> ConsensusResult {
    let dim = 128;
    let mut vecs = vec![]; let mut finals = vec![];
    for s in finals_json {
        vecs.push(embed(s, dim));
        finals.push(s.clone());
    }
    let mut groups: Vec<Vec<usize>> = vec![]; let mut reps: Vec<usize> = vec![];
    for i in 0..vecs.len() {
        let mut placed = false;
        for (gidx, rep) in reps.iter().enumerate() {
            if cosine(&vecs[i], &vecs[*rep]) >= 0.85 { groups[gidx].push(i); placed = true; break; }
        }
        if !placed { reps.push(i); groups.push(vec![i]); }
    }
    let scores = groups.iter().map(|g| (g.len() as f32) / (finals.len().max(1) as f32)).collect();
    let representatives = reps.iter().map(|i| (*i, finals[*i].clone())).collect();
    ConsensusResult { finals, representatives, groups, scores }
}
