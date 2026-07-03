#!/usr/bin/env python3
import json
import subprocess
from datetime import datetime
from itertools import product
from pathlib import Path

import click
import yaml


def run_command(command, cwd, failure_message):
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except FileNotFoundError as exc:
        raise click.ClickException("Julia executable was not found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(f"{failure_message} (exit code {exc.returncode}).") from exc

@click.command()
@click.option('--scenarios-file', '-s',
              type=click.Path(exists=True),
              default='scenarios.yml',
              help='YAML with islands, years, scenarios, cleans, island_params, co2_limits.')
@click.option('--run-script', '-r',
              type=click.Path(exists=True),
              default='run_model.jl',
              help='Path to your Julia entrypoint (run_model.jl).')
@click.option('--output-root', '-o',
              type=click.Path(),
              default='jobs',
              help='Directory under which to make per-scenario folders.')
@click.option('--bootstrap/--no-bootstrap', default=True,
              help='Instantiate the Julia project and validate Gurobi before running jobs.')
def main(scenarios_file, run_script, output_root, bootstrap):
    """Generate configs and run each scenario locally, reporting start & finish times."""
    repo_root = Path(__file__).resolve().parent
    run_script_path = Path(run_script).resolve()
    project_flag = f'--project={repo_root}'

    # load scenarios
    data = yaml.safe_load(Path(scenarios_file).read_text())
    islands       = data['islands']
    years         = data['years']
    scns          = data['scenarios']
    cleans        = data['cleans']
    island_params = data['island_params']
    co2_limits    = data['co2_limits']

    jobs_root = Path(output_root)
    jobs_root.mkdir(parents=True, exist_ok=True)

    if bootstrap:
        start = datetime.now()
        click.echo(f"[{start.isoformat()}] ▶ Preparing Julia environment")
        run_command(
            ['julia', project_flag, str(repo_root / 'bootstrap.jl')],
            cwd=repo_root,
            failure_message='Julia environment bootstrap failed'
        )
        end = datetime.now()
        click.echo(f"[{end.isoformat()}] ✅ Julia environment ready (took {end - start})\n")

    for isl, yr, scn, cln in product(islands, years, scns, cleans):
        name    = f"{scn}_{isl}_{yr}_{cln}"
        job_dir = jobs_root / name
        job_dir.mkdir(parents=True, exist_ok=True)

        # build config
        bau_val       = island_params.get(isl)
        if bau_val is None:
            raise click.ClickException(f"No island_params for '{isl}'")
        reduction_active = (yr == "2035" and cln == "clean")

        year_map = co2_limits.get(yr, {})
        co2_lim  = year_map.get(isl)
        if co2_lim is None:
            raise click.ClickException(f"No co2_limits for '{isl}' in year '{yr}'")

        cfg = {
            'island':            isl,
            'year':              yr,
            'scenario':          scn,
            'clean':             cln,
            'CO235reduction':    reduction_active,
            'BAUCO2emissions':   (bau_val if reduction_active else 0.0),
            'CO2_limit':         co2_lim
        }
        # optional model parameters passed through from the scenario YAML
        for key in ('mipgap', 'RE_limit', 'import_price', 'village_storage_max_mwh', 'connection_cost_scale', 'lp_method', 'battery_duration_h'):
            if key in data:
                cfg[key] = data[key]
        (job_dir / 'config.json').write_text(json.dumps(cfg, indent=2))

        # run
        start = datetime.now()
        click.echo(f"[{start.isoformat()}] ▶ Starting job {name}")
        run_command(
            [
                'julia',
                project_flag,
                str(run_script_path),
                '--config',
                str((job_dir / 'config.json').resolve()),
            ],
            cwd=repo_root,
            failure_message=f"Job {name} failed"
        )
        end = datetime.now()
        elapsed = end - start
        click.echo(f"[{end.isoformat()}] ✅ Completed {name} (took {elapsed})\n")

    click.echo("🎉 All scenarios finished.")

if __name__ == '__main__':
    main()

