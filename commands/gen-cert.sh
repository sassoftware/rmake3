#!/bin/bash
#
# Copyright (c) rPath, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
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
