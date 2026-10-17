# [Cosecha Propia](https://www.youtube.com/watch?v=Zcb8yPEItwA) Skills

Coleccion personal de skills que planeo usar en mis proyectos.

Construidas siguiendo el estandar de [skills.sh](https://skills.sh).

## Skills Disponibles

| Skill | Descripcion |
|-------|-------------|
| [no-sycophancy](skills/no-sycophancy/SKILL.md) | Elimina comportamiento adulador: sin elogios vacios, sin disculpas excesivas, sin rodeos innecesarios. Se activa bajo demanda con `/no-sycophancy`. |
| [pr-walkthrough](skills/pr-walkthrough/SKILL.md) | Screencast narrado de un PR o demo: Playwright graba, Fish Audio TTS narra en español, ffmpeg muxea a MP4 y opcionalmente se adjunta al PR. |
| [jira-evidence](skills/jira-evidence/SKILL.md) | Prepara evidencia auditable por criterio de aceptación Jira: matriz aprobada, videos locales revisables, comandos de test y referencias de código, sin publicar artefactos. |

## Instalacion

Usa el CLI de [skills.sh](https://skills.sh) (`npx skills`). En modo interactivo elige **Symlink** (recomendado: una sola copia) o **Copy**. `--copy` fuerza copia. `-y` (sin prompts) puede copiar; si ya tienes este repo clonado, enlaza a mano al directorio de skills del agente.

```bash
# Instala el pack (interactivo: elige skills, agentes y symlink vs copy)
npx skills add CristianG5401/cosecha-propia-skills

# Lista las skills del repo sin instalar
npx skills add CristianG5401/cosecha-propia-skills --list

# Una skill concreta, global, en un agente
npx skills add CristianG5401/cosecha-propia-skills --skill pr-walkthrough -g -a grok -y

# Clone local: el enlace apunta a este repo (sin duplicar)
ln -sfn "$(pwd)/skills/pr-walkthrough" ~/.grok/skills/pr-walkthrough
# Enlace directo para el alias compartido de agentes
ln -s "$(pwd)/skills/jira-evidence" ~/.agents/skills/jira-evidence
```

Flags utiles: `-g` global (`~/.<agente>/skills/`), `-a` agente (`grok`, `claude-code`, `cursor`, …), `-s`/`--skill` nombre, `-y` sin prompts, `--all` todo a todos los agentes.

```bash
npx skills list          # instaladas
npx skills update        # actualizar
npx skills remove <name> # quitar
```

`pr-walkthrough` trae scripts Node. Tras instalarla:

```bash
cd skills/pr-walkthrough && npm install
```

Tambien hace falta `ffmpeg` / `ffprobe` en el PATH y Fish Audio MCP (o `FISH_API_KEY`).

`jira-evidence` requiere Node.js 22+ (`npx`), `ffmpeg` y `ffprobe` en el PATH. Renderiza con HyperFrames (`hyperframes@0.8.155`, vía `npx`), que descarga un Chrome headless (~200 MB) a `~/.cache/hyperframes` en el primer render. No necesita dependencias Python externas.

## Estructura del Proyecto

```
cosecha-propia-skills/
└── skills/
    └── <nombre-skill>/
        ├── SKILL.md
        ├── scripts/      # opcional
        └── references/   # opcional
```

Cada `SKILL.md` sigue este formato:

```markdown
---
name: nombre-de-la-skill
description: Cuando y como usar esta skill
---

# Instrucciones de la skill aqui
```
