---
description: "prompt"
---
You are preparing to hand off your work to another agent. Your task is to generate a structured prompt that will help the next agent understand the current context, what you've accomplished, and transition toward a new vague objective.

## Behavior

When the user types `/prompt` (with or without additional instructions), you must:

1. **Analyze your past context** - Review what you were working on, what you've accomplished, and what discoveries you made during your work
2. **Capture the user's vague idea** - Accept a very general objective without details (e.g., "relancer l'entraînement", "optimiser les performances")
3. **Create a logical link** - Explain how your past work and discoveries have naturally led to this new idea from the user
4. **Generate a structured handoff prompt** following the 4 mandatory sections with strong exploratory collaboration instructions
5. **Create a transition plan using the plan tool** - Use the `create_plan` tool (with merge=false) to create a transition plan that will be automatically saved to the repository. This replaces the former markdown code block approach.

## Language Requirement

**MANDATORY**: The generated prompt must ALWAYS be written in French. When the agent addresses the user and creates the handoff prompt, it must be entirely in French language. Internal reasoning or tool calls can be in any language, but all user-facing content (the prompt itself) must be in French.

## Format Structure (Mandatory)

Create a transition plan with exactly these 4 sections integrated into the plan structure:

### **1. Contexte** (Part of plan overview and body)
Write in French. Explain the narrative of your work: what task you were working on, what you accomplished, and what you discovered during your work. Then explain how these discoveries/accomplishments naturally led to the user's new vague idea. This section should tell a story of progression and logical transition. Use high-level natural language without technical details, focusing on the journey from your work to this new exploration.

Integrate this narrative into the plan's overview section and include it as the opening section in the plan body.

### **2. Objectif** (Part of plan overview and body)
Write in French. Describe the very vague, general objective that the user has provided (a single line, a broad idea without details). Frame it as an open exploration rather than a precise task. DO NOT ask for details or precision - accept the vagueness. Examples in French: "Explorer la possibilité de relancer l'entraînement" rather than "Configurer et exécuter un pipeline d'entraînement avec paramètres spécifiques".

Include this objective in both the plan's overview and as a dedicated section in the plan body.

### **3. Fichiers Concernés** (Dedicated section in plan body)
Write in French. List TWO categories of files/directories:
- **Files from your past work**: Include files you modified or examined, with explanation of what was done/discovered in them
- **Files relevant to the new vague objective**: Include files that might be pertinent for exploration, with explanation of why they could be important

Indicate clearly which files belong to which category in your list. This becomes a dedicated section in the plan body.

### **4. Instructions de Collaboration** (Dedicated section in plan body)
Write in French. **MANDATORY AND CRITICAL**: This section must be extremely directive and imperative. You MUST specify that the agent:
- **FORBIDDEN** to start implementing anything immediately
- **MUST** read EXHAUSTIVELY all files listed in "Fichiers Concernés" before any action
- **MUST** perform multiple semantic searches in the codebase to understand existing solutions
- **MUST** read the README and all relevant documentation
- **MUST** achieve a deep understanding of the context and project before any discussion
- **MUST** discuss with the user to clarify precise expectations, ask questions about technical constraints, and establish a detailed action plan together
- Only AFTER exhaustive exploration and collaborative planning, can any implementation begin

Emphasize that exploration is NOT optional - it's mandatory. This becomes a dedicated section in the plan body.

## Plan Transition Mechanics

### Current Plan Analysis

Before creating the transition plan, you MUST:

1. **Check if you have an active plan** - Look at your current todos and plan state
2. **Analyze the completion status of your todos**:
   - If ALL todos are `completed` → The current conversation is finished, this is a fresh start
   - If some todos are `pending` or `in_progress` → The plan is incomplete/interrupted, include remaining todos
3. **Determine the reason for handoff**:
   - Plan completed → User wants to continue in same context
   - Plan blocked → Different issue to resolve before resuming
   - Context shift → New direction needed

### Transition Plan Requirements

When creating the transition plan:

1. **Use the plan tool** (`create_plan` with `merge=false`) - This automatically saves the plan to the repository
2. **Include all 4 sections** (Contexte, Objectif, Fichiers Concernés, Instructions) in the plan structure as described above
3. **Add remaining todos** (if any) - Copy all non-completed todos from your current plan to the transition plan. These are the tasks the successor should complete after resolving any issues
4. **Add a cleanup todo as FIRST todo** - Add this as the very first todo in the transition plan:
   ```
   "Supprimer ce plan de transition (<FILENAME>) s'il existe dans le repository après avoir bien compris le contexte. Ce plan est temporaire et ne doit pas rester dans le repo."
   ```
   Replace `<FILENAME>` with the actual filename of the transition plan you create (e.g., "modifier-commande-prompt.plan.md" or whatever name you choose).

5. **Explain the handoff reason** in the plan's overview or Contexte section - Be explicit about why you're passing control
6. **Write everything in French** - Consistent with the existing requirement

### Plan Creation Process

The transition plan must:
- Be saved to the repository automatically via the plan tool
- Contain enough context for the successor to understand the situation
- Preserve any incomplete work (remaining todos)
- Include a cleanup instruction as the first todo
- Be structured exactly like any other plan (with overview, body, and todos)

## Usage Modes

### Mode 1: With User Instructions
```
/prompt [user instructions]
```

In this mode:
- Generate the standard 4-section prompt with a narrative context showing your work progression
- Incorporate the user's vague idea in the **Objectif** section (accept the vagueness)
- Explain in **Contexte** how your completed work and discoveries led naturally to this vague idea
- The next agent will receive: your work narrative + the vague new objective + strong exploration mandate

### Mode 2: Without User Instructions
```
/prompt
```

In this mode:
- Generate the standard 4-section prompt based solely on your work
- Focus on explaining what you accomplished and obstacles you encountered
- Optionally suggest potential next steps or openings in **Instructions de Collaboration**, but make it clear the user will decide what happens next

## Example Output

Note: When you generate a transition plan using this command, you must use the `create_plan` tool and ALWAYS write everything in French.

### Example call to create_plan:

```json
{
  "merge": false,
  "overview": "Transition vers optimisation des performances d'authentification - Contexte: J'ai terminé l'implémentation du flux d'inscription d'authentification utilisateur et découvert lors des tests en charge des problèmes de performance significatifs avec des requêtes d'authentification qui ralentissent exponentiellement sous charge. Objectif: Explorer la possibilité d'optimiser le système d'authentification pour améliorer les performances.",
  "plan": "## Contexte\n\nJe travaillais sur l'implémentation d'un système d'authentification utilisateur pour l'application. J'ai terminé le flux d'inscription et l'ai rendu fonctionnel, avec toutes les validations nécessaires et les interactions avec la base de données. Lors des tests en charge, j'ai découvert que le système rencontre des problèmes de performance significatifs. Les utilisateurs rapportent des temps de réponse lents aux heures de pointe, et mes tests ont confirmé que les requêtes d'authentification prennent exponentiellement plus de temps avec l'augmentation de l'accès concurrent. Ce goulot d'étranglement de performance impacte directement l'expérience utilisateur. Compte tenu de ces découvertes, tu as suggéré d'explorer des stratégies d'optimisation pour le système d'authentification.\n\n## Objectif\n\nExplorer la possibilité d'optimiser le système d'authentification pour améliorer les performances sous charge.\n\n## Fichiers Concernés\n\n*Du travail que je viens de compléter :*\n- `src/auth/registration.js` : Contient la logique d'inscription que j'ai implémentée ; découvert des requêtes de base de données lourdes qui pourraient être optimisées\n- `src/config/database.js` : Configuration que j'ai examinée ; pourrait nécessiter des ajustements de pool de connexions\n- `tests/performance/load_test.js` : Tests de charge que j'ai exécutés qui ont révélé le goulot d'étranglement\n\n*Potentiellement pertinents pour l'exploration :*\n- `src/auth/login.js` : Pourrait contenir des patterns similaires à l'inscription qui nécessitent une optimisation\n- `src/config/` : Fichiers de configuration pour les limites de ressources qui pourraient être ajustées\n- `package.json` : Dépendances qui pourraient être mises à jour ou optimisées pour de meilleures performances\n\n## Instructions de Collaboration\n\nTu es INTERDIT de commencer à implémenter quoi que ce soit immédiatement. Ta première et UNIQUE tâche est l'exploration et la compréhension :\n\n1. **LIS EXHAUSTIVEMENT** tous les fichiers listés ci-dessus dans \"Fichiers Concernés\" - tu dois comprendre ce qui a été fait, ce qui a été découvert, et ce qui pourrait être pertinent\n2. **EFFECTUE plusieurs recherches sémantiques** dans le codebase pour identifier des solutions existantes, des patterns, ou du code connexe\n3. **LIS le README** et toute documentation pertinente pour comprendre l'architecture du projet et les contraintes\n4. **ATTEINS une compréhension approfondie** du contexte, du travail effectué, et de l'espace de problèmes\n5. **DISCUTE avec l'utilisateur** pour clarifier ses attentes précises, poser des questions sur les contraintes techniques, comprendre les priorités, et établir ensemble un plan d'action détaillé\n\nSeulement APRÈS avoir complété cette exploration exhaustive et cette planification collaborative, tu peux commencer à considérer tout travail d'implémentation. L'exploration est OBLIGATOIRE, pas optionnelle.",
  "todos": [
    {
      "id": "cleanup-transition-plan",
      "content": "Supprimer ce plan de transition (optimiser-performances-auth.plan.md) s'il existe dans le repository après avoir bien compris le contexte. Ce plan est temporaire et ne doit pas rester dans le repo.",
      "dependencies": []
    },
    {
      "id": "read-files",
      "content": "Lire exhaustivement tous les fichiers listés dans 'Fichiers Concernés' pour comprendre le contexte et les découvertes",
      "dependencies": ["cleanup-transition-plan"]
    }
  ]
}
```

### Important notes about the example:

- `merge: false` ensures the plan is saved as a new file to the repository
- The overview provides a concise summary of the context and objective
- The plan body contains all 4 required sections in French
- The first todo is ALWAYS the cleanup instruction to remove the transition plan
- If there were incomplete todos from the previous plan, they would be added here (after the cleanup todo)

## Important Notes

- **Always write the plan in French** - The entire transition plan must be in French language
- **Always use the exact 4-section structure** - This ensures consistency and clarity
- **Contexte must be narrative** - Tell the story of your work, discoveries, and transition to the new vague idea
- **Objectif must be vague** - Accept the user's general idea without demanding details
- **Fichiers Concernés must list both categories** - Your past work files AND files potentially relevant to the new vague objective
- **Instructions de Collaboration must be extremely strong** - Use imperative, forbidding language to enforce exhaustive exploration before any action
- **Emphasize exploration over execution** - The goal is collaborative planning after thorough understanding, not immediate implementation
- **Always add cleanup todo first** - The first todo must be to delete the transition plan file
- **Include remaining todos** - If your current plan had incomplete todos, copy them to the transition plan (after cleanup todo)
- **Use create_plan tool** - Never generate a markdown block, always use the `create_plan` tool with `merge=false`

