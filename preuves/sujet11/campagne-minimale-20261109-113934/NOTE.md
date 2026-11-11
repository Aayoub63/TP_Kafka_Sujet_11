# Note sur cette campagne

L'essai `r3-at_most_once-normale` est INVALIDE : le Mac s'est mis en veille
sur batterie pendant l'essai (journal `pmset`, de 12:33 environ à 13:50:53),
et l'horloge de Docker est passée d'un décalage de -0,891 s à -994,709 s.
Il a été refait après la campagne : `r3bis-at_most_once-normale`, réussite,
pause de 3,377 s. Le résumé écarte l'essai invalide.

Observation sans conclusion : en at-most-once, la pause vaut 4,416 s (r1)
et 4,454 s (charge forte, autre campagne), contre environ 3,4 à 3,5 s pour
les autres essais de la minimale. Deux essais ne suffisent pas pour dire si
c'est lié à la sémantique.
