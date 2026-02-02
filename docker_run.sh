docker run -d \
  --name mobile-portainer-api \
  --restart unless-stopped \
  --gpus all \
  -p 8001:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "/root/mobile_portainer/data:/app/data" \
  -v /:/hostfs:ro \
  -e ADMIN_USER="admin" \
  -e ADMIN_PASSWORD="password" \
  -e IGNORED_EVENTS="exec_create,exec_start,exec_die" \
  -e GIT_AUTO_UPDATE=true \
  -e GIT_REPO_URL="https://github.com/CodeFuckee/mobile_portainer.git" \
  -e GIT_BRANCH=main \
  -e GIT_CHECK_INTERVAL=60 \
  -e GIT_SSL_NO_VERIFY=true \
  -e HOST_FILESYSTEM_ROOT=/hostfs \
  mobile_portainer-api