import os

from .inventory.shared import powershell_json, run_hidden


def _is_computer_account(value: str) -> bool:
    """Computer accounts end in ``$`` and must never be assigned to a person."""
    local_part = (value or "").strip().split("@", 1)[0]
    return local_part.endswith("$")


def _clean_claims(claims: dict | None) -> dict:
    """Normalize identity output and reject service/computer account fallbacks."""
    cleaned = {key: str(value).strip() for key, value in (claims or {}).items()
               if value is not None and str(value).strip()}
    candidate = str(cleaned.get("email") or cleaned.get("user_principal_name") or "").strip().lower()
    if not candidate or _is_computer_account(candidate):
        return {}
    for key in ("email", "user_principal_name"):
        if key in cleaned:
            cleaned[key] = cleaned[key].lower()
    return cleaned


def observed_user_claims(override: str = "") -> dict:
    """Return identity hints for the interactive Windows user.

    The enterprise agent runs as LocalSystem, so ``whoami`` identifies the
    service account rather than the person using the computer. Win32 provides
    the interactive DOMAIN\\user value; Active Directory lookup adds the UPN,
    directory object id and employee id when they are available.
    """
    if override and "@" in override:
        email = override.strip().lower()
        # An early installer build could persist an AD computer account as an
        # override (for example ``MRWS-FRANK$@example.com``).  Never allow that
        # value to short-circuit the normal interactive-user discovery below.
        overridden = _clean_claims({"email": email, "user_principal_name": email,
                                     "source": "installer_override"})
        if overridden:
            return overridden
    if os.name != "nt":
        return {}
    try:
        claims = powershell_json(r"""
          $interactive=(Get-CimInstance Win32_ComputerSystem).UserName;
          # The collector runs as LocalSystem.  If WMI cannot see the active
          # desktop session, recover the owner of Explorer instead of falling
          # back to the computer's own AD account.
          if (-not $interactive -or $interactive -match '\\?\$$') {
            $interactive=Get-CimInstance Win32_Process -Filter "Name='explorer.exe'" | ForEach-Object {
              $owner=Invoke-CimMethod -InputObject $_ -MethodName GetOwner;
              if($owner.ReturnValue -eq 0 -and $owner.User -and $owner.User -notmatch '\$$'){
                if($owner.Domain){ "$($owner.Domain)\\$($owner.User)" } else { $owner.User }
              }
            } | Select-Object -First 1;
          }
          if (-not $interactive) { [pscustomobject]@{}; exit }
          $parts=$interactive -split '\\',2; $domain=if($parts.Count -gt 1){$parts[0]}else{''};
          $account=if($parts.Count -gt 1){$parts[1]}else{$parts[0]};
          $upn=''; $objectId=''; $employeeId='';
          try {
            $escaped=$account.Replace('\\','\\5c').Replace('*','\\2a').Replace('(','\\28').Replace(')','\\29');
            $result=([adsisearcher]"(&(objectCategory=person)(objectClass=user)(sAMAccountName=$escaped))").FindOne();
            if($result){
              $upn=[string]$result.Properties.userprincipalname[0];
              $employeeId=[string]$result.Properties.employeeid[0];
              if($result.Properties.objectguid[0]){$objectId=(New-Object Guid (,$result.Properties.objectguid[0])).Guid}
            }
          } catch {}
          [pscustomobject]@{email=$upn;user_principal_name=$upn;account_name=$account;
            domain=$domain;directory_object_id=$objectId;employee_id=$employeeId;source='interactive_session'}
        """)
        cleaned = _clean_claims(claims)
        if cleaned:
            return cleaned
    except Exception:
        pass
    code, output, _ = run_hidden(["whoami.exe", "/upn"], timeout=5)
    candidate = output.strip().lower()
    return ({"email": candidate, "user_principal_name": candidate, "source": "whoami_upn"}
            if code == 0 and "@" in candidate and " " not in candidate and not _is_computer_account(candidate)
            else {})


def observed_user_email(override: str = "") -> str | None:
    return observed_user_claims(override).get("email")
