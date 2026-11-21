use reqwest::blocking::Client;
use semver::Version;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::io::{Read, Write};

const REPO: &str = "https://github.com/L1nuxc/PrimeCloud/releases/download/";

pub fn check(client: &Client) -> Result<bool, Box<dyn std::error::Error>> {
    let response = client
        .get("https://api.github.com/repos/L1nuxc/PrimeCloud/releases/latest")
        .send()?;
    if response.status().as_u16() == 404 {
        return Ok(false);
    }
    let release: Value = response.error_for_status()?.json()?;
    let tag = release["tag_name"].as_str().ok_or("Missing release tag")?;
    let version = Version::parse(tag.strip_prefix('v').ok_or("Invalid release tag")?)?;
    if !version.pre.is_empty() || version <= Version::parse(env!("CARGO_PKG_VERSION"))? {
        return Ok(false);
    }
    let asset = release["assets"]
        .as_array()
        .and_then(|assets| assets.iter().find(|a| a["name"] == "PrimeCloud.exe"))
        .ok_or("Missing Windows release")?;
    let url = format!("{REPO}{tag}/PrimeCloud.exe");
    if asset["browser_download_url"] != url {
        return Err("Unexpected release URL".into());
    }
    let expected = asset["digest"]
        .as_str()
        .and_then(|d| d.strip_prefix("sha256:"))
        .ok_or("Missing GitHub SHA256")?;
    let size = asset["size"]
        .as_u64()
        .filter(|s| (1..=100_000_000).contains(s))
        .ok_or("Invalid size")?;
    let mut input = client.get(url).send()?.error_for_status()?.take(size + 1);
    let mut temp = tempfile::Builder::new().suffix(".exe").tempfile()?;
    let mut hash = Sha256::new();
    let mut buffer = [0; 65536];
    loop {
        let n = input.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        temp.write_all(&buffer[..n])?;
        hash.update(&buffer[..n]);
    }
    temp.flush()?;
    if temp.as_file().metadata()?.len() != size || hex::encode(hash.finalize()) != expected {
        return Err("Release digest mismatch".into());
    }
    let path = temp.into_temp_path();
    self_replace::self_replace(&path)?;
    Ok(true)
}
