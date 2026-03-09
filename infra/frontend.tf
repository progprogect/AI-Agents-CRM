# The application uses a unified Docker image (root Dockerfile) that runs
# nginx + FastAPI + Next.js inside a single container — the same architecture
# as Railway. This matches the existing deployment model exactly.
#
# There is no separate frontend ECS service or ECR repository.
# The backend ECS service (ecs.tf) uses the unified image and exposes
# port 80 via nginx, which internally routes to FastAPI (8000) and
# Next.js (3000).
#
# If you ever need to split backend and frontend into separate services
# (e.g., for independent scaling), you would:
#   1. Create separate Dockerfiles for backend/ and frontend/
#   2. Create a new ECR repository for the frontend image
#   3. Add a frontend ECS task definition and service here
#   4. Update alb.tf to route /api/* and /ws/* to backend, rest to frontend
