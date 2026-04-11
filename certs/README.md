# RAUC Bundle Signing Certificates
#
# This directory contains the CA and signing certificates for RAUC bundles.
#
# Files:
#   ca.cert.pem      - CA certificate (public, committed to repo)
#   ca.key.pem       - CA private key (NEVER commit, in .gitignore)
#   signing.cert.pem - Signing certificate (public, committed to repo)
#   signing.key.pem  - Signing private key (NEVER commit, in .gitignore)
#
# To generate development certificates:
#
#   # Generate CA key and certificate
#   openssl req -x509 -newkey rsa:4096 -nodes \
#     -keyout ca.key.pem -out ca.cert.pem \
#     -subj "/O=Apollo/CN=Apollo RAUC CA" -days 3650
#
#   # Generate signing key and CSR
#   openssl req -newkey rsa:4096 -nodes \
#     -keyout signing.key.pem -out signing.csr.pem \
#     -subj "/O=Apollo/CN=Apollo RAUC Signing"
#
#   # Sign with CA
#   openssl x509 -req -in signing.csr.pem \
#     -CA ca.cert.pem -CAkey ca.key.pem -CAcreateserial \
#     -out signing.cert.pem -days 3650
#
#   # Clean up
#   rm -f signing.csr.pem ca.srl
