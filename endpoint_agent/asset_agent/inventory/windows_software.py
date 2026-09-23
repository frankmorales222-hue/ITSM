from .shared import as_list, powershell_json


def collect_software() -> list[dict]:
    raw = powershell_json("""
      $paths=@('HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*','HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*','HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*');
      @($paths | ForEach-Object {Get-ItemProperty $_ -ErrorAction SilentlyContinue} | Where-Object {$_.DisplayName} |
        Select-Object @{n='name';e={$_.DisplayName}},@{n='version';e={$_.DisplayVersion}},@{n='publisher';e={$_.Publisher}},@{n='install_date';e={$_.InstallDate}} |
        Sort-Object name,version -Unique)
    """, timeout=40, default=[])
    return as_list(raw)
