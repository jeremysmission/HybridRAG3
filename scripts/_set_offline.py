"""Set config mode to offline — called by api_mode_commands.ps1"""
import yaml
with open('config/default_config.yaml', 'r') as f:
    cfg = yaml.safe_load(f)
cfg['mode'] = 'offline'
with open('config/default_config.yaml', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False)
print('Mode set to: offline')
