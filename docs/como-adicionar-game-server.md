# Como Adicionar um Novo Game Server

Guia para subir um novo servidor de jogo no cluster, seguindo o padrao
estabelecido pelo Palworld. Funciona para qualquer jogo com imagem Docker
e servidor dedicado Linux (Valheim, Terraria, Minecraft, etc).

## Visao geral do padrao

Cada game server segue a mesma estrutura:

```
k8s/games/<jogo>/
├── namespace.yaml     # namespace isolado por jogo
├── pvc.yaml           # PV + PVC no disco secundario (/var/lib/rancher/<jogo>)
├── deployment.yaml    # container do servidor + env vars + recursos
├── service.yaml       # NodePort para as portas do jogo
└── README.md          # documentacao especifica
```

Princípios:
- Cada jogo em seu proprio namespace (isolamento)
- Saves sempre no disco secundario via StorageClass `local-storage`
- Senhas via Secret (nunca commitadas)
- Portas expostas via NodePort no range 30000-32767
- `strategy: Recreate` (PV ReadWriteOnce nao permite rolling update)

---

## Passo a passo

### 1. Pesquisar a imagem Docker do servidor

Procure imagens maduras e mantidas. Boas fontes:
- Docker Hub (filtrar por downloads e ultima atualizacao)
- linuxserver.io (imagens padronizadas e bem documentadas)
- Repositorios oficiais do jogo

Anote: porta(s) do jogo, protocolo (UDP/TCP), RAM recomendada,
variaveis de ambiente de configuracao.

### 2. Criar a estrutura de pastas

  mkdir -p ~/Documents/wol-rpi-k8s/k8s/games/<jogo>

### 3. Criar o diretorio de storage no disco secundario

  sudo mkdir -p /var/lib/rancher/<jogo>
  sudo chown 1000:1000 /var/lib/rancher/<jogo>

> Ajuste o UID:GID conforme o usuario interno da imagem (geralmente 1000:1000).

### 4. namespace.yaml

  apiVersion: v1
  kind: Namespace
  metadata:
    name: <jogo>

### 5. pvc.yaml

Copie o do Palworld e ajuste: nome, namespace, tamanho e o `path` local.
Lembre de manter `storageClassName: local-storage` e o `nodeAffinity`
apontando para o hostname do node (andre-reis-hm570).

### 6. deployment.yaml

Pontos de atencao:
- `strategy: type: Recreate` (obrigatorio com PV ReadWriteOnce)
- `image:` a imagem escolhida
- `ports:` portas do container
- `env:` variaveis de configuracao do jogo
- Senhas via `secretKeyRef` (nunca em texto puro)
- `resources:` request/limit de memoria e CPU compativeis com o i9
- `volumeMounts` + `volumes` apontando para o PVC

### 7. service.yaml

  apiVersion: v1
  kind: Service
  metadata:
    name: <jogo>-service
    namespace: <jogo>
  spec:
    type: NodePort
    selector:
      app: <jogo>-server
    ports:
      - name: game
        port: <porta-interna>
        targetPort: <porta-interna>
        protocol: UDP
        nodePort: <30000-32767>

> IMPORTANTE: nodePort deve estar entre 30000-32767. Se a porta nativa do
> jogo estiver fora desse range (ex: 27015), escolha um nodePort valido
> (ex: 30015) - o cliente conecta na porta externa.

### 8. Criar o Secret (se o jogo tiver senhas)

  kubectl create secret generic <jogo>-secrets \
    --namespace <jogo> \
    --from-literal=admin-password='...' \
    --from-literal=server-password='...'

### 9. Aplicar

  kubectl apply -f k8s/games/<jogo>/namespace.yaml
  kubectl apply -f k8s/games/<jogo>/pvc.yaml
  kubectl apply -f k8s/games/<jogo>/deployment.yaml
  kubectl apply -f k8s/games/<jogo>/service.yaml

### 10. Acompanhar o primeiro boot

  kubectl get pods -n <jogo> -w
  kubectl logs -f -n <jogo> deployment/<jogo>-server

### 11. Port forwarding no roteador

Acesse http://192.168.15.1 -> Port Forwarding e adicione:
`<nodePort>/<protocolo>` -> `192.168.15.14`

### 12. Commitar

  cd ~/Documents/wol-rpi-k8s
  git pull
  git add k8s/games/<jogo>/
  git commit -m "feat: add servidor <jogo>"
  git push origin main

O ArgoCD pode sincronizar automaticamente se a pasta estiver no escopo
da Application, ou aplica-se manualmente com kubectl.

---

## Checklist rapido

- [ ] Imagem Docker pesquisada e validada
- [ ] Diretorio /var/lib/rancher/<jogo> criado com permissoes corretas
- [ ] namespace, pvc, deployment, service criados
- [ ] strategy: Recreate no deployment
- [ ] nodePort no range 30000-32767
- [ ] Secret criado (se aplicavel)
- [ ] Recursos (RAM/CPU) compativeis com o i9
- [ ] Port forwarding configurado no roteador
- [ ] README.md documentado
- [ ] Commitado no Git

---

## Jogos compativeis testados/recomendados

| Jogo | Imagem | RAM | Server Linux |
|------|--------|-----|--------------|
| Palworld | thijsvanloef/palworld-server-docker | 8-16GB | Sim |
| Valheim | lloesche/valheim-server | 2-4GB | Sim |
| Terraria | ryshe/terraria | 1GB | Sim |
| Minecraft | itzg/minecraft-server | 2-6GB | Sim |

> Jogos sem servidor dedicado Linux (ex: The Forest, Sons of the Forest)
> NAO sao compativeis com esta arquitetura.

---

## Monitoramento no painel (opcional)

Se o jogo expoe uma API de metricas (como a REST API do Palworld), e
possivel exibir status no painel do RPi:

1. Exponha a porta da API como NodePort no service.yaml
2. Adicione as variaveis no .env do painel (URL, user, pass)
3. Crie um fragmento `_<jogo>.html` em site/templates/
4. Adicione uma rota `/<jogo>-fragment` no app.py
5. Adicione o card no dashboard.html com hx-get e hx-trigger

Veja a implementacao do Palworld como referencia.
