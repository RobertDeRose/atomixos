# RAUC Bundle Signing Certificates

Development signing keys are committed to the repo (prefixed with `dev.`).
These are NOT production secrets — they only sign dev/test bundles.

Production devices use a separate CA and signing key provisioned through
a secure channel (HSM, secrets manager, etc.).

## Files

| File                   | Purpose                         | Committed?     |
|------------------------|---------------------------------|----------------|
| `dev.ca.cert.pem`      | Development CA certificate      | Yes            |
| `dev.ca.key.pem`       | Development CA private key      | Yes (dev only) |
| `dev.signing.cert.pem` | Development signing certificate | Yes            |
| `dev.signing.key.pem`  | Development signing private key | Yes (dev only) |

## Regenerating development certificates

```sh
# Generate CA key and certificate
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout dev.ca.key.pem -out dev.ca.cert.pem \
  -subj "/O=Dev/CN=Dev RAUC CA" -days 3650

# Generate signing key and CSR
openssl req -newkey rsa:4096 -nodes \
  -keyout dev.signing.key.pem -out signing.csr.pem \
  -subj "/O=Dev/CN=Dev RAUC Signing"

# Sign with CA
openssl x509 -req -in signing.csr.pem \
  -CA dev.ca.cert.pem -CAkey dev.ca.key.pem -CAcreateserial \
  -out dev.signing.cert.pem -days 3650

# Clean up
rm -f signing.csr.pem dev.ca.srl
```
