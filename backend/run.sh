source venv/bin/activate
set -a
source ./.env
set +a
export PYTHONPATH=$(pwd)/..
flask run
