"""QR code utility for LHDN e-Invoice compliance.

Generates base64-encoded PNG QR code images from LHDN MyInvois URLs
for embedding in Salary Slip print formats.
"""
import base64
import io

import qrcode


def generate_qr_code_base64(url):
	"""Convert a URL to a base64-encoded PNG data URI for inline rendering.

	Args:
		url: The URL to encode as a QR code. If falsy (empty string, None),
			returns empty string without error.

	Returns:
		A string like 'data:image/png;base64,...' or empty string if url is falsy.
	"""
	if not url:
		return ""

	qr = qrcode.make(url)
	buffer = io.BytesIO()
	qr.save(buffer, format="PNG")
	encoded = base64.b64encode(buffer.getvalue()).decode()
	return f"data:image/png;base64,{encoded}"
