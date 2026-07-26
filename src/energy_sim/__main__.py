"""Entry point: ``python -m energy_sim {export,cost-report,validate}``."""
import sys

from energy_sim.interface.cli import main

if __name__ == "__main__":
    sys.exit(main())
