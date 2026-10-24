# kanban.it – versione statica

Mirror statico di <https://www.kanban.it> (WordPress), pubblicato con GitHub Pages dalla cartella `docs/`.

## Rigenerare il sito

```bash
tools/build.sh
```

Lo script:
1. raccoglie l'elenco delle pagine dalle API REST di WordPress (le pagine vivono sotto `/it/`);
2. scarica il sito con `wget` (pagine + CSS/JS/immagini/font) in `docs/`, più la pagina 404 di WordPress come `404.html`;
3. esegue `tools/postprocess.py`, che:
   - ripulisce i nomi dei file (`?ver=…`);
   - rimuove i riferimenti al backend WordPress (feed, oEmbed, xmlrpc, emoji), Google Analytics e il banner cookie (plugin GDPR Cookie Compliance);
   - rende relativi i link al dominio (il sito mescola `http` e `https` e `wget` non li converte tutti);
   - corregge i link `?p=NN` del menu e i link relativi scritti male (es. `it/supermarket` dentro `/it/`);
   - sposta il link Privacy dal menu principale al footer, accanto al copyright;
   - sostituisce la home `/` con un redirect a `/it/`, come sul sito originale.

Se il dominio punta già a GitHub Pages, per riscaricare il WordPress originale serve aggiungere temporaneamente a `/etc/hosts` la riga `3.123.199.162 www.kanban.it` (lo script si ferma con un avviso se il WordPress non è raggiungibile).

I file in `static/`, se presenti, vengono copiati in `docs/` a ogni build. Per un dominio personalizzato, creare un file `CNAME` nella root del repo: `build.sh` lo copia in `docs/`.
