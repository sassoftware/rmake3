#!/bin/bash
#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


CONFFILE=$(mktemp /tmp/gen-x509-XXXXXXXX)

FQDN=$(hostname)
[ -z "$FQDN" ] && FQDN=localhost.localdomain

OPENSSL=/usr/bin/openssl
CERTFILE=$(mktemp /tmp/gen-x509-crt-XXXXXXXX)
KEYFILE=$(mktemp /tmp/gen-x509-key-XXXXXXXX)

# Create config file
cat << EOF > $CONFFILE
configdir=/etc/ssl

default_bits = 1024
distinguished_name  = sect_DN
prompt              = no

[ v3_req ]
basicConstraints    = CA:FALSE
nsCertType          = server
subjectKeyIdentifier    = hash
authorityKeyIdentifier  = keyid,issuer:always
keyUsage            = nonRepudiation, digitalSignature, keyEncipherment

[ sect_DN ]
countryName         = --
stateOrProvinceName = --
localityName        = --
organizationName    = Auto-Generated
organizationalUnitName  = Self-Signed Certificate
commonName          = ${FQDN}
EOF

# Generate self-signed cert and key
$OPENSSL req -new -x509 -text -config $CONFFILE -out $CERTFILE -set_serial $(date +%s) -extensions v3_req -days 365 -newkey rsa:1024 -keyout $KEYFILE -rand /dev/urandom -nodes 2> /dev/null

cat $CERTFILE $KEYFILE
rm -f $CONFFILE $CERTFILE $KEYFILE
