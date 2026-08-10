"""Firma XAdES-BES de comprobantes electrónicos (SRI Ecuador).

Firma el elemento raíz `<factura id="comprobante">` con RSA-SHA1.
La estructura replica la del firmador `ec-sri-invoice-signer`
(probado contra el SRI de pruebas con certificados reales):

- Tres Referencias en SignedInfo: documento (#comprobante, transform
  enveloped), SignedProperties (Type XAdES) y KeyInfo (certificado).
- KeyInfo con X509Data + KeyValue (RSA modulus/exponent).
- SignedProperties con SigningTime, SigningCertificate y
  DataObjectFormat.
"""
import base64
import re
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from lxml import etree

DS_NS = 'http://www.w3.org/2000/09/xmldsig#'
ETSI_NS = 'http://uri.etsi.org/01903/v1.3.2#'
C14N = 'http://www.w3.org/TR/2001/REC-xml-c14n-20010315'
ENVELOPED = 'http://www.w3.org/2000/09/xmldsig#enveloped-signature'
RSA_SHA1 = 'http://www.w3.org/2000/09/xmldsig#rsa-sha1'
SHA1 = 'http://www.w3.org/2000/09/xmldsig#sha1'
SIGNED_PROPS_TYPE = 'http://uri.etsi.org/01903#SignedProperties'

_XPATH = etree.XPath('//ds:Signature', namespaces={'ds': DS_NS})


def _c14n(el):
    return etree.tostring(el, method='c14n', with_comments=False)


def _b64(data):
    return base64.b64encode(data).decode('ascii')


def _el(parent, tag, ns=None, text=None, **attrs):
    et = '{%s}%s' % (ns, tag) if ns else tag
    el = etree.SubElement(parent, et)
    if text is not None:
        el.text = str(text)
    for k, v in attrs.items():
        el.set(k, str(v))
    return el


def _issuer_name(cert):
    """Nombre del emisor del certificado en formato RFC4514 (legible)."""
    return cert.issuer.rfc4514_string().replace(',', ', ')


def _ruc_del_certificado(cert):
    """Extrae el RUC del certificado (campo `RUC:`, serialNumber o 13 dígitos)."""
    from app.orders.validators import es_ruc_valido

    sujeto = cert.subject.rfc4514_string()
    candidatos = []

    m = re.search(r'RUC\s*[:=]\s*(\d{13})', sujeto, re.IGNORECASE)
    if m:
        candidatos.append(m.group(1))

    for attr in cert.subject:
        if attr.oid == NameOID.SERIAL_NUMBER and isinstance(attr.value, str):
            m2 = re.search(r'(\d{13})', attr.value)
            if m2:
                candidatos.append(m2.group(1))

    candidatos += re.findall(r'(?<!\d)(\d{13})(?!\d)', sujeto)

    for ruc in candidatos:
        if es_ruc_valido(ruc):
            return ruc
    return None


def obtener_ruc_bytes(datos_p12, clave_p12):
    """Devuelve el RUC embebido en el certificado de un .p12, o None.

    `datos_p12` son los bytes del archivo (permite validar una firma
    recién subida sin guardarla en disco). Los certificados emitidos por
    las entidades del SRI (Security Data, ANF, BCE) llevan el RUC del
    titular en el sujeto; si no se encuentra un RUC válido se devuelve
    None. Lanza ValueError si la clave es incorrecta.
    """
    key, cert, _ = pkcs12.load_key_and_certificates(
        datos_p12, clave_p12.encode('utf-8')
    )
    if cert is None:
        return None
    return _ruc_del_certificado(cert)


def obtener_ruc_certificado(ruta_p12, clave_p12):
    """Devuelve el RUC embebido en el certificado de un .p12, o None."""
    with open(ruta_p12, 'rb') as f:
        return obtener_ruc_bytes(f.read(), clave_p12)


def _sha1_b64(data):
    h = hashes.Hash(hashes.SHA1())
    h.update(data)
    return _b64(h.finalize())


def firmar_xml_bytes(xml_bytes, ruta_p12, clave_p12):
    """Firma un XML de factura SRI y devuelve el XML firmado en bytes."""
    with open(ruta_p12, 'rb') as f:
        key, cert, _ = pkcs12.load_key_and_certificates(
            f.read(), clave_p12.encode('utf-8')
        )
    if key is None or cert is None:
        raise ValueError('El archivo .p12 no contiene clave privada y certificado.')

    doc = etree.fromstring(xml_bytes)
    raiz = doc
    if raiz.get('id') != 'comprobante':
        raise ValueError('El XML no tiene el atributo id="comprobante".')

    sufijo = uuid.uuid4().hex[:8]
    id_doc_ref = 'DocumentRef-%s' % sufijo
    id_props = 'SignedProperties-%s' % sufijo
    id_props_ref = 'SignedPropertiesRef-%s' % sufijo
    id_keyinfo = 'Certificate-%s' % sufijo
    id_keyinfo_ref = 'CertificateRef-%s' % sufijo

    # ---------- Armado de la firma ----------
    firma = etree.Element('{%s}Signature' % DS_NS, Id='Signature-%s' % sufijo)
    signed_info = etree.SubElement(firma, '{%s}SignedInfo' % DS_NS,
                                   Id='SignedInfo-%s' % sufijo)
    _el(signed_info, 'CanonicalizationMethod', DS_NS, Algorithm=C14N)
    _el(signed_info, 'SignatureMethod', DS_NS, Algorithm=RSA_SHA1)

    # 1) Referencia al documento (transform enveloped, primero)
    ref_doc = etree.SubElement(
        signed_info, '{%s}Reference' % DS_NS, Id=id_doc_ref, URI='#comprobante'
    )
    transforms = etree.SubElement(ref_doc, '{%s}Transforms' % DS_NS)
    _el(transforms, 'Transform', DS_NS, Algorithm=ENVELOPED)
    _el(ref_doc, 'DigestMethod', DS_NS, Algorithm=SHA1)
    digest_doc = _el(ref_doc, 'DigestValue', DS_NS)

    # 2) Referencia a las SignedProperties (sin transforms, Type XAdES)
    ref_props = etree.SubElement(
        signed_info, '{%s}Reference' % DS_NS,
        Id=id_props_ref, Type=SIGNED_PROPS_TYPE, URI='#%s' % id_props,
    )
    _el(ref_props, 'DigestMethod', DS_NS, Algorithm=SHA1)
    digest_props = _el(ref_props, 'DigestValue', DS_NS)

    # 3) Referencia al KeyInfo (certificado)
    ref_keyinfo = etree.SubElement(
        signed_info, '{%s}Reference' % DS_NS,
        Id=id_keyinfo_ref, URI='#%s' % id_keyinfo,
    )
    _el(ref_keyinfo, 'DigestMethod', DS_NS, Algorithm=SHA1)
    digest_keyinfo = _el(ref_keyinfo, 'DigestValue', DS_NS)

    _el(firma, 'SignatureValue', DS_NS, Id='SignatureValue-%s' % sufijo)

    key_info = etree.SubElement(firma, '{%s}KeyInfo' % DS_NS, Id=id_keyinfo)
    x509_data = etree.SubElement(key_info, '{%s}X509Data' % DS_NS)
    _el(x509_data, 'X509Certificate', DS_NS, _b64(cert.public_bytes(serialization.Encoding.DER)))
    pub = key.public_key().public_numbers()
    mod_bytes = pub.n.to_bytes((pub.n.bit_length() + 7) // 8, 'big')
    exp_bytes = pub.e.to_bytes((pub.e.bit_length() + 7) // 8, 'big')
    key_value = etree.SubElement(key_info, '{%s}KeyValue' % DS_NS)
    rsa_key = etree.SubElement(key_value, '{%s}RSAKeyValue' % DS_NS)
    _el(rsa_key, 'Modulus', DS_NS, _b64(mod_bytes))
    _el(rsa_key, 'Exponent', DS_NS, _b64(exp_bytes))

    obj = etree.SubElement(firma, '{%s}Object' % DS_NS,
                           Id='SignatureObject-%s' % sufijo)
    qual = etree.SubElement(obj, '{%s}QualifyingProperties' % ETSI_NS,
                            Target='#Signature-%s' % sufijo)
    signed_props = etree.SubElement(qual, '{%s}SignedProperties' % ETSI_NS,
                                    Id=id_props)
    signed_sig_props = etree.SubElement(signed_props, '{%s}SignedSignatureProperties' % ETSI_NS)
    ahora = datetime.now(dt_timezone(timedelta(hours=-5)))
    _el(signed_sig_props, 'SigningTime', ETSI_NS,
        ahora.strftime('%Y-%m-%dT%H:%M:%S') + '-05:00')
    signing_cert = etree.SubElement(signed_sig_props, '{%s}SigningCertificate' % ETSI_NS)
    cert_el = etree.SubElement(signing_cert, '{%s}Cert' % ETSI_NS)
    cert_digest = etree.SubElement(cert_el, '{%s}CertDigest' % ETSI_NS)
    _el(cert_digest, 'DigestMethod', DS_NS, Algorithm=SHA1)
    digest_cert = _el(cert_digest, 'DigestValue', DS_NS)
    issuer_serial = etree.SubElement(cert_el, '{%s}IssuerSerial' % ETSI_NS)
    _el(issuer_serial, 'X509IssuerName', DS_NS, _issuer_name(cert))
    _el(issuer_serial, 'X509SerialNumber', DS_NS, str(cert.serial_number))
    signed_data_obj = etree.SubElement(
        signed_props, '{%s}SignedDataObjectProperties' % ETSI_NS
    )
    data_obj = etree.SubElement(
        signed_data_obj, '{%s}DataObjectFormat' % ETSI_NS,
        ObjectReference='#%s' % id_doc_ref,
    )
    _el(data_obj, 'Description', ETSI_NS, 'Firma digital')
    _el(data_obj, 'MimeType', ETSI_NS, 'text/xml')
    _el(data_obj, 'Encoding', ETSI_NS, 'UTF-8')

    # ---------- Cálculo de digestos ----------
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    digest_cert.text = _sha1_b64(cert_der)

    # Digest del documento SIN la firma (la transform enveloped la excluye).
    digest_doc.text = _sha1_b64(_c14n(raiz))

    # La firma debe estar adjunta para que los namespaces en scope
    # (xmlns:ds y xmlns:xades) queden correctos al canonicar.
    raiz.append(firma)
    digest_props.text = _sha1_b64(_c14n(signed_props))
    digest_keyinfo.text = _sha1_b64(_c14n(key_info))

    # ---------- Firma ----------
    firma_bytes = key.sign(
        _c14n(signed_info),
        padding.PKCS1v15(),
        hashes.SHA1(),
    )
    firma.find('{%s}SignatureValue' % DS_NS).text = _b64(firma_bytes)

    return etree.tostring(
        raiz, xml_declaration=True, encoding='UTF-8', pretty_print=False
    )
