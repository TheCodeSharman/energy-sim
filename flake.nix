{
  description = "Home energy-cost / scenario simulator (Python, DDD). Pure-stdlib runtime; pytest for dev.";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      python = pkgs.python313;
    in {
      devShells.${system}.default = pkgs.mkShell {
        packages = [
          python
          python.pkgs.pytest
        ];

        # Runtime is pure stdlib; src/ is importable in-place via PYTHONPATH.
        shellHook = ''
          export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
          echo "energy-sim devenv ready: $(python --version), pytest $(pytest --version 2>&1 | head -1)"
        '';
      };
    };
}
