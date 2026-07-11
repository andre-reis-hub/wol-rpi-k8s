# Configuração do Grafana — Embed + Login Admin (coexistindo)

Estas env vars fazem o Grafana permitir EMBED anônimo (iframes no painel)
E login de admin ao mesmo tempo. Descoberto após muita tentativa e erro.

## Aplicar (via kubectl set env)

```
kubectl set env deployment/monitoring-grafana -n monitoring \
  GF_AUTH_ANONYMOUS_ENABLED=true \
  GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer \
  GF_SECURITY_ALLOW_EMBEDDING=true \
  GF_SECURITY_COOKIE_SAMESITE=none \
  GF_SECURITY_COOKIE_SECURE=true \
  GF_AUTH_DISABLE_LOGIN_FORM=false \
  GF_SERVER_ROOT_URL=https://grafana.areis-solution.com
```

## Por que cada uma

- ANONYMOUS_ENABLED=true + ANONYMOUS_ORG_ROLE=Viewer -> iframes funcionam sem login
- ALLOW_EMBEDDING=true -> permite <iframe> (senão o navegador bloqueia)
- COOKIE_SAMESITE=none -> cookie funciona dentro de iframe cross-site
- COOKIE_SECURE=true -> OBRIGATORIO com SameSite=none. Sem isso, o navegador
  REJEITA o cookie de sessao e o login admin "volta pra tela de login".
  (Este era o bug: login sem erro de senha mas nao persistia.)
- DISABLE_LOGIN_FORM=false -> mantem o formulario de login acessivel mesmo
  com anonimo ligado (senao o anonimo esconde o login = loop)
- SERVER_ROOT_URL=https://... -> Grafana sabe que e servido via HTTPS
  (Cloudflare Tunnel termina o TLS). Necessario para cookies/redirects.

## IMPORTANTE — mover para os values do Helm

O ideal e colocar isso nos values do kube-prometheus-stack (secao grafana.env),
para persistir se o Grafana for recriado. Exemplo:

grafana:
  env:
    GF_AUTH_ANONYMOUS_ENABLED: "true"
    GF_AUTH_ANONYMOUS_ORG_ROLE: "Viewer"
    GF_SECURITY_ALLOW_EMBEDDING: "true"
    GF_SECURITY_COOKIE_SAMESITE: "none"
    GF_SECURITY_COOKIE_SECURE: "true"
    GF_AUTH_DISABLE_LOGIN_FORM: "false"
    GF_SERVER_ROOT_URL: "https://grafana.areis-solution.com"

## Login admin
Usuario/senha no secret monitoring-grafana (keys admin-user / admin-password).
