from .shared import powershell_json, run_hidden


def collect_management() -> dict:
    domain = powershell_json("""
      $cs=Get-CimInstance Win32_ComputerSystem;
      [pscustomobject]@{domain_joined=$cs.PartOfDomain;domain_name=if($cs.PartOfDomain){$cs.Domain}else{$null};workgroup=if(-not $cs.PartOfDomain){$cs.Workgroup}else{$null}}
    """)
    code, output, _ = run_hidden(["dsregcmd.exe", "/status"], timeout=15)
    def state(name: str) -> str:
        if code != 0:
            return "Unknown"
        for line in output.splitlines():
            if line.strip().lower().startswith(name.lower()):
                return "Joined" if line.split(":", 1)[-1].strip().upper() == "YES" else "Not Joined"
        return "Unknown"
    domain.update({"entra_joined": state("AzureAdJoined"), "workplace_joined": state("WorkplaceJoined")})
    return domain
