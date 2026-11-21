fn main() {
    if std::env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc") {
        println!("cargo:rustc-link-arg-bin=primecloud=/MANIFEST:EMBED");
        println!("cargo:rerun-if-changed=primecloud.manifest");
        println!(
            "cargo:rustc-link-arg-bin=primecloud=/MANIFESTINPUT:{}/primecloud.manifest",
            env!("CARGO_MANIFEST_DIR")
        );
    }
}
