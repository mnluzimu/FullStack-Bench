cd /mnt/cache/agent/Zimu/OpenHands/src/docker

docker build -t openhands-postgres .
docker tag openhands-postgres:latest luzimu/openhands-postgres:latest

python /mnt/cache/agent/Zimu/OpenHands/src/tests/convo_with_docker_sandboxed_server.py

python /mnt/cache/agent/Zimu/OpenHands/src/tests/test_single_run.py

docker push luzimu/openhands-postgres:latest
