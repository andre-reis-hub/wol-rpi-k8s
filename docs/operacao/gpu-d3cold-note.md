# GPU GTX 1660 — erro D3cold (monitor preto esporadico)

## Sintoma
- nvidia-smi: "Unable to determine device handle / Unknown Error"
- dmesg: "Unable to change power state from D3cold to D0, device inaccessible"
- Monitor sem sinal (preto) esporadico. GPU cai do barramento.

## Causa
Power management PCIe agressivo joga a GPU em D3cold e ela nao acorda.

## Correcao (GRUB)
Editar /etc/default/grub, na linha GRUB_CMDLINE_LINUX_DEFAULT adicionar:
  pcie_port_pm=off pcie_aspm.policy=performance

Manter tambem: nvidia.NVreg_EnableGpuFirmware=0
NAO usar pcie_aspm=off (tira video neste hardware).

Depois: sudo update-grub && sudo reboot

## Mitigacao runtime (sem reboot, previne recorrencia)
echo "0" | sudo tee /sys/bus/pci/devices/0000:01:00.0/d3cold_allowed

## Se persistir mesmo com as flags
Pode ser hardware (a GTX 1660 ja dava sinais de instabilidade). Testar
outra GPU ou verificar alimentacao/reassentar a placa.
