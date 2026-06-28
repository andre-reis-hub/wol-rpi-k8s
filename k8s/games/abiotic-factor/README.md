# Abiotic Factor Server

Servidor dedicado de Abiotic Factor rodando via `andrewsav/abiotic-factor`
(servidor Windows sob Wine, dentro de container Linux).

## Configuracao

- Jogadores: 6
- Roda via Wine (jogo nao tem servidor Linux nativo)
- Save persistido em /var/lib/rancher/abiotic-factor (disco secundario, 25Gi)
- Arquitetura: AMD64 apenas (i9 e compativel)

## IMPORTANTE - como a senha funciona nesta imagem

Diferente do Palworld, a imagem do Abiotic Factor (AndrewSav) recebe TODA a
configuracao numa unica string de linha de comando (variavel `args`), incluindo
a senha via `-ServerPassword=`. O Kubernetes nao interpola secret dentro de
outra env var, entao temos duas opcoes:

### Opcao A (usada aqui) - senha na args via patch local, fora do Git

O deployment.yaml versionado NAO contem a senha. Apos aplicar, adicione a senha
com um patch que fica so no cluster:

  kubectl set env deployment/abiotic-factor-server -n abiotic-factor \
    args="-userdir=/server/AbioticFactor/Saved -newconsole -useperfthreads -NoAsyncLoadingThread -UseMultithreadForDS -MaxServerPlayers=6 -PORT=7777 -QUERYPORT=27015 -ServerName=Servidor-do-Andre-Abiotic -SaveName=Mundo -SteamServerName=Servidor-do-Andre-Abiotic -ServerPassword=tico"

Assim a senha nunca vai para o GitHub. O ArgoCD com self-heal pode reverter
isso - por isso, para o Abiotic, recomenda-se criar a Application SEM self-heal
(igual fizemos no Palworld, so automated).

### Opcao B - aceitar a senha no Git (NAO recomendado)

Colocar -ServerPassword=tico direto no deployment.yaml. Simples, mas expoe a
senha no repositorio publico. Evite.

## Portas (NodePort)

| Porta externa | Protocolo | Uso |
|---------------|-----------|-----|
| 30777 | UDP | Porta do jogo (mapeada para 7777 interno) |
| 30016 | UDP | Query/Steam (mapeada para 27015 interno) |

## Port forwarding no roteador

Aba "Redirecionar Portas" do roteador Vivo:
- 30777 UDP -> 192.168.15.14 (IP Externo VAZIO!)
- 30016 UDP -> 192.168.15.14 (IP Externo VAZIO!)

> Lembrete: NAO travar o campo "IP Externo" - deixar vazio. Foi o que causou
> o problema de acesso no Palworld.

## Conectar

No jogo: "Join a Server" -> "Direct Connect" -> IP Address.
- Local: 192.168.15.14:30777
- Externo: IP_PUBLICO:30777
- Senha: tico

## Primeiro boot

O primeiro start baixa o servidor via SteamCMD (~15-20GB, AppID 2857200) e
depois inicializa o Wine. Pode demorar bastante. Acompanhar:

  kubectl logs -f -n abiotic-factor deployment/abiotic-factor-server

## Lobby code

A imagem mostra um codigo de lobby no log. Para encontrar:

  kubectl logs -n abiotic-factor deployment/abiotic-factor-server | grep -i code:
