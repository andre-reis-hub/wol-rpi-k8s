# Post-mortem — Perda do RPi (cartao SD corrompido)

Data do incidente: setembro/2026

## O que aconteceu
Quedas de energia repetidas num fim de semana corromperam o cartao SD do
Raspberry Pi Zero W que roda o painel (wol-panel) e o tunnel cloudflared.
Ao ligar, o notebook pediu pra formatar o cartao "de cara" (FS corrompido).
O RPi nao subia, nao pegava IP, nao aparecia no roteador.

## Causa raiz
- CAUSA IMEDIATA: corrupcao do sistema de arquivos do SD por cortes de energia
  durante escrita. O RPi escreve no SD constantemente; queda no meio de uma
  escrita corrompe. Varias quedas seguidas = corrupcao quase garantida.
- CAUSA DE FUNDO: sem no-break (UPS) e sem imagem de backup do cartao.

## Impacto
- Painel (controle dos jogos, ligar/desligar PC) fora do ar.
- Acesso externo pelos dominios (panel/grafana/argocd) fora do ar.
- OS SERVIDORES DE JOGO NAO foram afetados (rodam no i9, nao no RPi).
  A galera continuou jogando; so o controle remoto caiu.

## Por que a recuperacao foi trabalhosa (os buracos que este registro fecha)
1. O .env do painel nao estava salvo em lugar nenhum (so no SD). Tivemos que
   remontar cada variavel na mao, extraindo segredos do i9.
2. O tunnel cloudflared era do tipo LOCAL (config.yml + credenciais no RPi),
   e nao estava documentado que era assim nem como recuperar. As credenciais
   do tunnel se perderam com o SD e NAO da pra rebaixar da nuvem.
3. O config.yml.example do repo estava incompleto (faltava a rota do grafana).
4. O RPi Zero W e ARMv6 — precisou do cloudflared novo (>=2025) que voltou a
   ter binario ARMv6 funcional; versoes intermediarias davam "Illegal instruction".

## Como foi recuperado (resumo; passo a passo em docs/setup-rpi/)
1. Regravou o SD com Raspberry Pi OS Lite (SSH/WiFi/hostname no Imager).
2. Reinstalou painel: git clone, venv (com python3-full!), requirements, .env.
3. Remontou o .env extraindo segredos do i9 (token novo do cluster, etc).
4. Recriou a confianca SSH RPi->i9 (ssh-copy-id) + sudoers do shutdown.
5. Recuperou o cloudflared local: login, recriou o tunnel, gerou credenciais,
   montou config.yml com as 3 rotas, reapontou os CNAMEs, virou servico.

## Licoes / acoes preventivas
- [ ] GUARDAR O .env NO BITWARDEN. Foi o que mais custou remontar.
- [ ] Fazer imagem (.img) do cartao SD de tempos em tempos. Regravar a imagem
      teria transformado horas de recuperacao em minutos.
- [ ] No-break (UPS) para o RPi e o i9 — ataca a causa raiz (quedas de energia).
- [ ] Considerar reduzir escrita no SD (log2ram) para prolongar a vida do cartao.
- [x] Documentar o setup do RPi e o cloudflared local (este commit).
- OPCIONAL futuro: se o SD corromper de novo, considerar migrar o tunnel para
  o modo REMOTO (gerenciado pela nuvem), onde as rotas ficam salvas na Cloudflare
  e nao se perdem com o cartao. Por ora, mantido local (funciona).

## Detalhe tecnico: token do cluster que vazou
O token antigo da ServiceAccount panel-controller havia sido commitado por
engano no passado. Na recuperacao, geramos um token novo (kubectl create token
... --duration=8760h), o que naturalmente substitui o uso do antigo. Existe
ainda o secret legado panel-controller-token no cluster; pode ser removido.
