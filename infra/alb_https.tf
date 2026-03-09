# HTTPS Listener — forwards all traffic to the unified ECS container.
# nginx inside the container handles routing to FastAPI or Next.js.
# No separate listener rules are needed.
#
# To obtain an ACM certificate:
#   Option A (AWS-managed): AWS Console → Certificate Manager → Request → enter domain
#   Option B (Let's Encrypt import):
#     aws acm import-certificate \
#       --certificate fileb://cert.pem \
#       --private-key fileb://key.pem \
#       --certificate-chain fileb://chain.pem \
#       --region <region>
#
# Then set in terraform.tfvars:
#   certificate_arn = "arn:aws:acm:<region>:<account>:certificate/<id>"

resource "aws_lb_listener" "https" {
  count             = var.enable_alb && var.certificate_arn != "" ? 1 : 0
  load_balancer_arn = aws_lb.main[0].arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  # All traffic → unified container; nginx handles /api, /ws, / internally
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend[0].arn
  }
}
