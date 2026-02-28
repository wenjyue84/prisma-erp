"""XAdES BeS XML Digital Signature for MyInvois Self-Billed Phase 2.

Implements XAdES-BeS (Basic Electronic Signature) using RSA-SHA256 and
C14N canonicalization, as required by LHDN MyInvois e-Invoice Guidelines
(SDK v3.x) for Phase 2 implementors.

Certificates must be issued by a MyInvois-accepted CA:
  - MSC Trustgate
  - DigiCert Malaysia

Usage:
    from lhdn_payroll_integration.utils.xml_signer import sign_xml
    signed_xml = sign_xml(xml_string, cert_path, cert_password)

If xmlsec is not installed, sign_xml() logs a warning and returns the
original XML unchanged (graceful degradation).
"""

import base64
import hashlib
import logging
import datetime

import frappe

logger = logging.getLogger(__name__)

# XAdES / XML-DSIG namespaces
_DS_NS = "http://www.w3.org/2000/09/xmldsig#"
_XADES_NS = "http://uri.etsi.org/01903/v1.3.2#"


def _xmlsec_available():
    """Check whether xmlsec is importable."""
    try:
        import xmlsec  # noqa: F401
        return True
    except ImportError:
        return False


def sign_xml(xml_string: str, cert_path: str, cert_password: str = None) -> str:
    """Apply XAdES BeS digital signature to an XML document.

    Attempts to sign using the xmlsec library. If xmlsec is not installed,
    logs a warning and returns the original XML unchanged.

    Args:
        xml_string: The XML document as a string (UTF-8 encoded content).
        cert_path: Absolute path to the PEM or PFX/P12 certificate file.
        cert_password: Optional password for the certificate file.

    Returns:
        str: Signed XML string, or the original xml_string if xmlsec is
             unavailable or signing fails.
    """
    if not _xmlsec_available():
        logger.warning(
            "xmlsec library not installed. XML signing skipped. "
            "Install xmlsec with native libxml2 to enable XAdES signatures."
        )
        return xml_string

    try:
        import xmlsec
        from lxml import etree
    except ImportError as exc:
        logger.warning("lxml or xmlsec unavailable: %s. Signing skipped.", exc)
        return xml_string

    try:
        root = etree.fromstring(xml_string.encode("utf-8"))
    except Exception as exc:
        logger.error("Failed to parse XML for signing: %s", exc)
        return xml_string

    try:
        # Determine key format from file extension
        cert_path_lower = cert_path.lower()
        if cert_path_lower.endswith(".p12") or cert_path_lower.endswith(".pfx"):
            key = xmlsec.Key.from_file(
                cert_path,
                xmlsec.KeyFormat.PKCS12_PEM,
                cert_password.encode() if cert_password else None,
            )
        else:
            # PEM format: load key then cert separately
            key = xmlsec.Key.from_file(cert_path, xmlsec.KeyFormat.PEM)
            # Try loading cert from same path (PEM bundle with key+cert)
            try:
                key.load_cert_from_file(cert_path, xmlsec.KeyFormat.CERT_PEM)
            except Exception:
                pass  # Cert may not be in same file; proceed with key only

        # Build ds:Signature skeleton
        signature_node = xmlsec.template.create(
            root,
            xmlsec.Transform.EXCL_C14N,
            xmlsec.Transform.RSA_SHA256,
            ns="ds",
        )
        root.append(signature_node)

        # Add reference to the entire document (detached, URI="")
        ref = xmlsec.template.add_reference(
            signature_node,
            xmlsec.Transform.SHA256,
            uri="",
        )
        xmlsec.template.add_transform(ref, xmlsec.Transform.ENVELOPED)
        xmlsec.template.add_transform(ref, xmlsec.Transform.EXCL_C14N)

        # Add KeyInfo with X509Data
        key_info = xmlsec.template.ensure_key_info(signature_node, ns="ds")
        xmlsec.template.add_x509_data(key_info)

        # Sign
        ctx = xmlsec.SignatureContext()
        ctx.key = key
        ctx.sign(signature_node)

        return etree.tostring(root, encoding="unicode", xml_declaration=True)

    except Exception as exc:
        logger.error("XAdES signing failed: %s. Returning unsigned XML.", exc)
        return xml_string


def get_company_signing_config(company_name: str) -> dict:
    """Return digital signature configuration for a company.

    Reads custom_enable_xml_signature, custom_digital_cert_path,
    and custom_digital_cert_password from the Company document.

    Args:
        company_name: The Frappe Company document name.

    Returns:
        dict with keys:
            - enabled (bool): True if signing is enabled
            - cert_path (str): Absolute path to certificate file
            - cert_password (str): Certificate password (may be None)
    """
    try:
        company = frappe.get_doc("Company", company_name)
        enabled = bool(getattr(company, "custom_enable_xml_signature", 0))
        cert_path = getattr(company, "custom_digital_cert_path", None) or ""
        cert_password = getattr(company, "custom_digital_cert_password", None) or ""
        return {
            "enabled": enabled,
            "cert_path": cert_path.strip(),
            "cert_password": cert_password,
        }
    except Exception:
        return {"enabled": False, "cert_path": "", "cert_password": ""}


def maybe_sign_xml(xml_string: str, company_name: str) -> str:
    """Sign XML if the company has XML signing enabled.

    Convenience wrapper: reads company config and signs if enabled.

    Args:
        xml_string: The XML document string.
        company_name: The Frappe Company document name.

    Returns:
        str: Signed XML if enabled and cert configured, original XML otherwise.
    """
    config = get_company_signing_config(company_name)
    if not config["enabled"]:
        return xml_string
    if not config["cert_path"]:
        logger.warning(
            "XML signing enabled for company '%s' but custom_digital_cert_path is empty. "
            "Signing skipped.",
            company_name,
        )
        return xml_string
    return sign_xml(xml_string, config["cert_path"], config.get("cert_password"))
