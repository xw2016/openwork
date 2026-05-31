import yaml
for f in ['docker-compose.yml', 'docker-compose.dev.yml']:
    try:
        with open(f) as fh:
            yaml.safe_load(fh)
        print(f'OK: {f}')
    except Exception as e:
        print(f'ERR: {f} - {e}')
