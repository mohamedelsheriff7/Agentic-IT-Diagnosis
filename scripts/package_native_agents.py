"""Rebuild native import ZIPs from their editable YAML trees."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
for name in ('Routing_Agent', 'Escalation_Outage_Agent', 'IT_Support_Supervisor'):
    source = root / 'Agents' / name
    output = root / 'Agents' / 'ZIP' / (name + '.zip')
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob('*')):
            if path.is_file():
                archive.write(path, name + '/' + path.relative_to(source).as_posix())
    print(output)
