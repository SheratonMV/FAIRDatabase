set -e

source venv/bin/activate

set -a
source tests/.env.test
set +a

export PYTHONPATH=$(pwd):$(pwd)/..

pytest -m "not slow"
