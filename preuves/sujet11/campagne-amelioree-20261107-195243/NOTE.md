# Note sur cette campagne

La campagne a été lancée avec `./scripts/sujet11-campagne.sh 3 60 amelioree`.

L'essai `r1-at_least_once-normale` est écarté. Pendant cet essai, un second
essai a été lancé par un bouton du tableau de bord Grafana (dossier
`runtime/sujet11/20261107-185604-amelioree-at_least_once-normale`, heure UTC
du conteneur service-health). Ce second essai a recréé les conteneurs et
rejoué le flux. Le premier a donc fini en échec, « pas de reprise des
écritures », pour une raison qui ne vient pas de la solution testée.

Cause : rien n'empêchait un essai lancé par bouton de démarrer pendant un
essai lancé depuis le terminal. Correction : verrou d'essai unique dans
`scripts/sujet11-maj.sh` (branche `fix/maj-verrou-essai`).

L'essai a été refait sous verrou (`r1bis-at_least_once-normale`) : réussite,
pause de 1,022 s. C'est lui qui figure dans `resume.md`.
