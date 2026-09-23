NORTHSTAR DESK - INTERNAL HTTPS TRUST
=====================================

PURPOSE
Removes the browser certificate warning for the existing internal Northstar Desk HTTPS site.
No private key is exported or installed on client computers.

CREATE THE CLIENT PACKAGE (ON THE NORTHSTAR SERVER)
1. Run Create-Northstar-HTTPS-Trust-Package.cmd as an administrator.
2. The tool validates and exports Caddy's existing public root certificate.
3. It creates NorthstarDesk-HTTPS-Client-Trust.zip on the Public Desktop.

TEST ONE LAPTOP
1. Copy and fully extract NorthstarDesk-HTTPS-Client-Trust.zip.
2. Double-click Install-NorthstarDesk-HTTPS-Trust.cmd.
3. Approve the Windows administrator prompt.
4. Close every browser window, reopen the browser, and visit the Northstar HTTPS URL.

DEPLOY WITH GROUP POLICY
Import NorthstarDesk-Internal-Root-CA.cer into:
Computer Configuration > Policies > Windows Settings > Security Settings >
Public Key Policies > Trusted Root Certification Authorities

SECURITY NOTES
- Confirm the thumbprint in certificate-manifest.txt before wide deployment.
- Deploy only the public .cer file. Never distribute Caddy's private keys.
- DNS must resolve the exact Northstar hostname contained in the site URL.
- This package does not disable TLS validation.

SENTINELONE / INSTALLER TRUST
HTTPS trust and executable trust are separate controls. This certificate removes the website
TLS warning. It does not sign Northstar EXE files and cannot override SentinelOne policy.
Use an Authenticode code-signing certificate for the EXE, or have the SentinelOne administrator
approve the verified installer by signer/hash according to company security policy.

