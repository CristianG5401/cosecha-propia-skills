# [Cosecha Propia](https://www.youtube.com/watch?v=Zcb8yPEItwA) Skills

Coleccion personal de skills que planeo usar en mis proyectos.

Construidas siguiendo el estandar de [skills.sh](https://skills.sh).

## Skills Disponibles

| Skill | Descripcion |
|-------|-------------|
| [no-sycophancy](skills/no-sycophancy/SKILL.md) | Elimina comportamiento adulador: sin elogios vacios, sin disculpas excesivas, sin rodeos innecesarios. Se activa bajo demanda con `/no-sycophancy`. |

## Instalacion

Instala cualquier skill usando el CLI de [skills.sh](https://skills.sh/docs):

```bash
npx skills add CristianG5401/cosecha-propia-skills
```

Esto instalara las skills y las hara disponibles en tu agente de IA.

## Estructura del Proyecto

```
cosecha-propia-skills/
└── skills/
    └── <nombre-skill>/
        └── SKILL.md
```

Cada `SKILL.md` sigue este formato:

```markdown
---
name: nombre-de-la-skill
description: Cuando y como usar esta skill
---

# Instrucciones de la skill aqui
```
