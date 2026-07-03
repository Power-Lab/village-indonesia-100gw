#!/usr/bin/env python3
import json
import subprocess
from itertools import product
from pathlib import Path

import click
import yaml

@click.command()
@click.option('--scenarios-file', '-s',
              type=click.Path(exists=True),
              default='scenarios.yml',
              help='YAML with islands, years, scenarios, cleans, island_params, co2_limits.')
@click.option('--submit-script', '-b',
              type=click.Path(exists=True),
              default='submit_test.sb',
              help='SLURM script template filename.')
@click.option('--output-root', '-o',
              type=click.Path(),
              default='jobs',
              help='Directory to create per‑scenario job folders.')
@click.option('--submit/--no-submit', default=False,
              help='Whether to actually call sbatch on each folder.')
def main(scenarios_file, submit_script, output_root, submit):
    """
    Generate per‑scenario job dirs (with config.json & submit script)
    and optionally submit them to SLURM.
    """
    data          = yaml.safe_load(Path(scenarios_file).read_text())
    islands       = data['islands']
    years         = data['years']
    scns          = data['scenarios']
    cleans        = data['cleans']
    island_params = data['island_params']
    co2_limits    = data['co2_limits']

    jobs_root = Path(output_root)
    jobs_root.mkdir(parents=True, exist_ok=True)

    for isl, yr, scn, cln in product(islands, years, scns, cleans):
        name    = f"{scn}_{isl}_{yr}_{cln}"
        job_dir = jobs_root / name
        job_dir.mkdir(parents=True, exist_ok=True)

        # BAUCO2 and active‐flag
        bau_val  = island_params.get(isl)
        if bau_val is None:
            raise click.ClickException(f"No island_params entry for '{isl}'")
        reduction_active = (yr == "2035" and cln == "clean")

        # CO2_limit lookup
        year_map = co2_limits.get(yr, {})
        co2_lim  = year_map.get(isl)
        if co2_lim is None:
            raise click.ClickException(f"No co2_limits entry for '{isl}' in year '{yr}'")

        # build config
        cfg = {
            'island':             isl,
            'year':               yr,
            'scenario':           scn,
            'clean':              cln,
            'CO235reduction':     reduction_active,
            'BAUCO2emissions':    (bau_val if reduction_active else 0.0),
            'CO2_limit':          co2_lim
        }
        # optional model parameters passed through from the scenario YAML
        for key in ('mipgap', 'RE_limit', 'import_price', 'village_storage_max_mwh', 'connection_cost_scale', 'lp_method', 'battery_duration_h'):
            if key in data:
                cfg[key] = data[key]
        (job_dir / 'config.json').write_text(json.dumps(cfg, indent=2))

        # symlink the SLURM submit script
        sb_link = job_dir / Path(submit_script).name
        if sb_link.exists():
            sb_link.unlink()
        sb_link.symlink_to(Path(submit_script).resolve())

        # ≤9‑char SLURM job name
        job_code = f"{scn[:3].upper()}{isl[:2].upper()}{yr[-2:]}{cln[0].upper()}"

        click.echo(f"Prepared job '{name}' (code '{job_code}')")
        if submit:
            subprocess.run(
                ["sbatch", "--job-name", job_code, sb_link.name],
                cwd=job_dir,
                check=True
            )
            click.echo(f"  Submitted as SLURM job '{job_code}'")

    total = len(islands) * len(years) * len(scns) * len(cleans)
    click.echo(f"\n✅ Done: set up {total} job(s) under '{jobs_root}'")

if __name__ == '__main__':
    main()
