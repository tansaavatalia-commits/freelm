# Spostamento nel repository dedicato (D-001)

Oggi il progetto vive nella cartella `game-portal/` del branch
`claude/game-portal-master-mm5azl` di `freelm`. Quando il repository `game-portal` esiste:

## Cosa devi fare tu (una volta, gratis)
1. Su GitHub: **New repository** → nome `game-portal` → **Private** → **senza** README,
   .gitignore o licenza (deve essere vuoto).
2. Dimmi il nome esatto (es. `tansaavatalia-commits/game-portal`): lo collego alla sessione.

## Cosa faccio io (preserva tutta la storia dei commit)
```bash
git subtree split --prefix=game-portal -b game-portal-export
git push <nuovo-repo> game-portal-export:main
```
Il risultato è un repository in cui `game-portal/` diventa la radice, con la storia
di ogni file. Poi verifico `pnpm install && pnpm check && pnpm e2e` sul nuovo repo e la CI.

## Dopo lo spostamento
- In `freelm` la cartella resta solo su questo branch (nessun impatto su `main`).
  Il branch potrà essere eliminato quando confermi che il nuovo repo è completo.
