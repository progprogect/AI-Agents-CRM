# HTTPS Listener for ALB
# Requires an ACM certificate. Request one via:
#   AWS Console → Certificate Manager → Request → Enter your domain
# or import a Let's Encrypt certificate with:
#   aws acm import-certificate --certificate file://cert.pem --private-key file://key.pem \
#     --certificate-chain file://chain.pem --region <region>
#
# Then set certificate_arn in your terraform.tfvars:
#   certificate_arn = "arn:aws:acm:<region>:<account>:certificate/<id>"

resource "aws_lb_listener" "frontend_https" {
  count             = var.enable_alb && var.certificate_arn != "" ? 1 : 0
  load_balancer_arn = aws_lb.main[0].arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"  # TLS 1.3 preferred
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend[0].arn
  }
}

# HTTPS: API routes → backend
resource "aws_lb_listener_rule" "backend_api_https" {
  count        = var.enable_alb && var.certificate_arn != "" ? 1 : 0
  listener_arn = aws_lb_listener.frontend_https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend[0].arn
  }

  condition {
    path_pattern {
      values = ["/api/*", "/health", "/docs", "/openapi.json"]
    }
  }
}

# HTTPS: WebSocket routes → backend
resource "aws_lb_listener_rule" "backend_websocket_https" {
  count        = var.enable_alb && var.certificate_arn != "" ? 1 : 0
  listener_arn = aws_lb_listener.frontend_https[0].arn
  priority     = 90

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend[0].arn
  }

  condition {
    path_pattern {
      values = ["/ws/*"]
    }
  }
}
