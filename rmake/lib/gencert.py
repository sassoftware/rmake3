#!/usr/bin/python
import optparse
import os
import random
import sys
import tempfile
import time
from M2Crypto import ASN1, EVP, RSA, X509
from M2Crypto import threading as m2threading


E_VALUE = 65537


def new_cert(keySize, subject, expiry, issuer=None, issuer_evp=None,
  isCA=None, serial=None, extensions=None, e_value=E_VALUE):
    """
    Generate a new X509 certificate and RSA key.

    Returns the new RSA and X509 objects.

    @param keySize: Number of bits for the new RSA key
    @param subject: X509 subject for new certificate
    @param expiry: Number of days after which the new certificate
                   will expire
    @param issuer: X509 object giving the CA to which the new
                   certificate will be a client
    @param issuer_evp: EVP matching the issuer CA, for signing the new
                       certificate
    @param isCA: If C{True}, the new certificate will be a CA. If
                 C{False}, it will explicitly be a non-CA. If C{None},
                 no C{basicConstraints} extension will be attached.
    @param serial: Serial number of the new certificate.
    @param extensions: List of X509 extensions to add
    @param e_value: Value of C{e} to use when generating the new key.
    """

    # Generate RSA key and a matching EVP (signing helper).
    rsa = RSA.gen_key(keySize, e_value, lambda *_: None)
    evp = EVP.PKey()
    evp.assign_rsa(rsa, capture=False)

    # Create X509 object and assign parameters.
    now = long(time.time())
    not_before = ASN1.ASN1_UTCTIME()
    not_before.set_time(now)
    not_after = ASN1.ASN1_UTCTIME()
    not_after.set_time(now + expiry * 86400)

    if issuer is None:
        issuer = subject
        issuer_evp = evp

    if serial is None:
        serial = random.randint(1, (2**15) - 1)

    x509 = X509.X509()
    x509.set_pubkey(evp)
    x509.set_subject(subject)
    x509.set_issuer(issuer)
    x509.set_not_before(not_before)
    x509.set_not_after(not_after)
    x509.set_version(0x2)
    x509.set_serial_number(serial)

    # Add extensions to X509.
    if isCA is not None:
        constraints = X509.new_extension('basicConstraints',
            'CA:%s' % (isCA and 'TRUE' or 'FALSE'), critical=1)
        x509.add_ext(constraints)
    if extensions:
        for extension in extensions:
            x509.add_ext(extension)

    # Sign the certificate with the authority's EVP, or ours if this is
    # a self-sign certificate.
    x509.sign(issuer_evp, 'sha1')

    return rsa, x509


def new_sitename_extension(siteName):
    return X509.new_extension('subjectAltName',
        'email:%s@siteUserName.identifiers.rpath.internal' % siteName)


def name_from_options(options):
    name = X509.X509_Name()
    for field in ('C', 'ST', 'L', 'O', 'OU', 'CN'):
        value = getattr(options, field)
        if value:
            setattr(name, field, value)

    extensions = []
    if options.site_user:
        extensions.append(new_sitename_extension(options.site_user))

    return name, extensions


def new_ca(options, isCA=True):
    """
    Create a new self-signed certificate with or without CA capability
    and write it to file or standard output.

    @param options: Command-line options
    @param isCA: If C{True}, the new certificate will be a CA
    """
    subject, extensions = name_from_options(options)
    rsa, x509 = new_cert(options.key_length, subject, options.expiry,
        isCA=isCA, extensions=extensions)

    return writeCert(options, rsa, x509)


def new_client(options, isCA=False):
    """
    Create a new client certificate and write it to file or standard
    output.

    @param options: Command-line options
    @param isCA: If C{True}, the new certificate will be a CA
    """
    subject, extensions = name_from_options(options)

    ca_evp, ca_x509 = loadCA(options)
    issuer = ca_x509.get_subject()

    if os.path.exists(options.index_file):
        index = int(open(options.index_file).read().strip())
    else:
        index = 0
    index += 1
    open(options.index_file, 'w').write('%d\n' % index)

    rsa, x509 = new_cert(options.key_length, subject, options.expiry,
        issuer, ca_evp, isCA=False, serial=index, extensions=extensions)

    return writeCert(options, rsa, x509)


def loadCA(options):
    """
    Load a CA certificate to use for signing a client certificate.

    Returns a EVP for signing the client certificate, and a X509
    object for extracting information about the CA.

    @params options: Command-line options
    @return: (EVP, X509)
    """
    if not options.ca_cert:
        sys.exit("A CA certificate is required")

    ca_x509 = X509.load_cert(options.ca_cert)

    if options.ca_key:
        keyPath = options.ca_key
    else:
        keyPath = options.ca_cert
    ca_evp = EVP.load_key(keyPath)

    return ca_evp, ca_x509


def open_safe(path):
    """
    Securely create a non-world-readable file at C{path}, deleting
    any existing file at that path.

    Returns an open file object to the new file.
    """
    path = os.path.abspath(path)
    tmpFd, tmpPath = tempfile.mkstemp(dir=os.path.dirname(path))
    try:
        if os.path.exists(path):
            os.unlink(path)
        os.rename(tmpPath, path)
    except:
        os.close(tmpFd)
        os.unlink(tmpPath)
        raise

    return os.fdopen(tmpFd, 'w')


def writeCert(options, rsa, x509):
    """
    Write a new certificate C{x509} and private key C{rsa} as
    prescribed by the command-line C{options}.
    """
    if options.output:
        certOut = open_safe(options.output)
    else:
        certOut = sys.stdout

    if options.output_key and options.output_key != options.output:
        keyOut = open_safe(options.output_key)
    else:
        keyOut = certOut

    keyOut.write(rsa.as_pem(None))
    certOut.write(x509.as_pem())

    return 0


def main(args):
    parser = optparse.OptionParser()

    # Generate CA mode
    parser.add_option("-a", "--new-ca", action="store_true",
        help="Generate a self-sign CA certificate")
    parser.add_option("-s", "--self-sign", action="store_true",
        help="Generate a self-sign client certificate")
    parser.add_option("-n", "--new-client", action="store_true",
        help="Generate a signed client certificate")

    # Generate client mode
    parser.add_option("-c", "--ca-cert", help="Path to the CA certificate")
    parser.add_option("-C", "--ca-key",
        help="Path to the CA's key, if not stored with the certificate")

    # Options
    parser.add_option("-o", "--output", metavar="FILE",
        help="Write the new certificate to FILE")
    parser.add_option("-O", "--output-key", metavar="FILE",
        help="Write the new key to FILE (default: same as certificate)")
    parser.add_option("-L", "--key-length", metavar="BITS", type="int",
        help="Generate keys of size BITS")
    parser.add_option("-e", "--expiry", type="int",
        help="Certificate expires after this many days")

    parser.add_option("--site-user",
        help="Add a site-user altSubjectName field")

    for field in ('C', 'ST', 'L', 'O', 'OU', 'CN'):
        parser.add_option("--" + field, help="Add to the subject's name")

    parser.add_option("-i", "--index-file", metavar="FILE",
        help="File to use as the serial index")
    parser.set_defaults(key_length=2048, expiry=7, index_file='index.txt')

    options, args = parser.parse_args(args)
    if args:
        print "Unexpected argument"
        parser.print_help()
        return 1

    m2threading.init()

    if options.new_ca:
        return new_ca(options)
    elif options.self_sign:
        return new_ca(options, False)
    elif options.new_client:
        return new_client(options)
    else:
        print "Must specify a command, one of -a -s -n"
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
