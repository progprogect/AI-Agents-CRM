# Application Load Balancer (optional — disabled by default for MVP)
# When enabled, ALL traffic hits the unified ECS container on port 80.
# nginx inside the container handles routing to FastAPI or Next.js internally.
resource "aws_lb" "main" {
  count              = var.enable_alb ? 1 : 0
  name               = "doctor-agent-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb[0].id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection       = false
  enable_http2                     = true
  enable_cross_zone_load_balancing = true

  tags = merge(local.common_tags, { Name = "doctor-agent-alb" })
}

# ALB Security Group — allow HTTP(80) and HTTPS(443) from internet
resource "aws_security_group" "alb" {
  count       = var.enable_alb ? 1 : 0
  name        = "doctor-agent-alb-sg"
  description = "ALB — allow HTTP and HTTPS from internet"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "doctor-agent-alb-sg" })
}

# Allow ALB to reach the unified ECS container on port 80 (nginx)
resource "aws_security_group_rule" "alb_to_ecs" {
  count                    = var.enable_alb ? 1 : 0
  type                     = "ingress"
  from_port                = 80
  to_port                  = 80
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.alb[0].id
  security_group_id        = aws_security_group.ecs_service.id
  description              = "ALB → ECS unified container (nginx)"
}

# Unified target group — port 80 (nginx inside the container)
# Stickiness is enabled for WebSocket support.
resource "aws_lb_target_group" "backend" {
  count       = var.enable_alb ? 1 : 0
  name        = "doctor-agent-app-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    path                = "/health"
    protocol            = "HTTP"
    matcher             = "200"
  }

  # Sticky sessions — needed for WebSocket connections to remain on the same task
  stickiness {
    enabled         = true
    type            = "lb_cookie"
    cookie_duration = 86400
  }

  deregistration_delay = 30

  tags = local.common_tags
}

# HTTP listener — redirect all traffic to HTTPS
resource "aws_lb_listener" "http_redirect" {
  count             = var.enable_alb ? 1 : 0
  load_balancer_arn = aws_lb.main[0].arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}
