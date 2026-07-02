# FASE 0 (revisada) — Particionamento com LVM

LVM permite expandir o disco no futuro SEM formatar. Um pouco mais de setup
agora, muita flexibilidade depois.

## No instalador do Ubuntu Desktop 24.04

Opcao mais simples: na tela de instalacao, escolha
"Advanced features" -> "Use LVM with the new Ubuntu installation".
Isso cria o esquema LVM automaticamente. MAS por padrao ele usa o disco todo
num volume so. Para ter root de 150GB, ajuste depois do 1o boot (abaixo).

## Esquema recomendado (disco de sistema ~238GB)

| Elemento | Tamanho | Observacao |
|----------|---------|------------|
| EFI | 512MB | particao normal (fora do LVM) |
| PV (Physical Volume) | resto do disco | vira o "pool" LVM |
| VG (Volume Group) "ubuntu-vg" | todo o PV | grupo de volumes |
| LV root | 150GB | / (ext4) |
| (espaco livre no VG) | ~85GB | reservado para expandir no futuro |

> Deixar espaco LIVRE no VG e a graca do LVM: da para crescer o root depois.

## Expandir o root no FUTURO (quando precisar) — guardar esta receita

```
# Ver espaco livre no volume group
sudo vgs
# Aumentar o LV root em +50GB (exemplo)
sudo lvextend -L +50G /dev/ubuntu-vg/ubuntu-lv
# Aumentar o filesystem para ocupar o novo espaco (ext4, online, sem umount!)
sudo resize2fs /dev/ubuntu-vg/ubuntu-lv
# Confirmar
df -h /
```

> Isso e feito COM O SISTEMA LIGADO, sem formatar, sem reboot. E o motivo de
> usar LVM. Se um dia o root apertar, sao 3 comandos.

## Disco de 526GB (k8s)

Esse fica FORA do LVM, como particao ext4 simples, montada por UUID em
/var/lib/rancher (ver Fase 1.3 do guia principal). Nao precisa de LVM porque
tem espaco de sobra (526GB) e a montagem por UUID ja resolve a estabilidade.

> Poderia usar LVM nele tambem, mas manter simples: 1 particao ext4 por UUID.
