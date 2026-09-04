# instagram-publisher

Script para publicar posts de imagem única ou carrosséis no Instagram via
Meta Graph API (App `Pluri_Midia-IG`, App ID `1513058077176813`).

## Como funciona

A Graph API não aceita upload binário direto para posts de feed — ela exige
uma `image_url` pública que os servidores da Meta conseguem buscar. Por isso
o script hospeda cada imagem antes de criar os containers de mídia.

Duas estratégias de hospedagem (`--host` ou `IMAGE_HOST_STRATEGY` no `.env`):

- **`github`** (padrão, recomendado) — copia a imagem para um repositório
  Git que você controla, faz commit e push, e usa a URL
  `raw.githubusercontent.com` resultante. As imagens ficam sob sua conta,
  auditáveis e você decide quando limpar o histórico.
- **`catbox`** — sobe a imagem para o catbox.moe, um host público e
  **anônimo**: qualquer pessoa com o link acessa o arquivo indefinidamente e
  você não tem controle sobre ele (sem login, sem exclusão garantida). Use
  só se tiver um motivo específico para não usar o GitHub.

Em qualquer uma das opções, **as imagens publicadas ficam públicas na
internet** — é assim que a Graph API consegue buscá-las. Isso é esperado
para conteúdo que já vai virar um post público no Instagram; não use o
script para imagens que não deveriam ficar acessíveis por link direto.

## Configuração

1. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

   (ou, se preferir sem arquivo de requirements: `pip install requests python-dotenv`)

2. Copie `.env.example` para `.env` neste mesmo diretório e preencha:

   ```bash
   cp .env.example .env
   ```

   | Variável | Descrição |
   |---|---|
   | `INSTAGRAM_BUSINESS_ID` | ID da conta comercial/criador do Instagram |
   | `FACEBOOK_PAGE_ID` | ID da Página do Facebook vinculada |
   | `INSTAGRAM_ACCESS_TOKEN` | Token de acesso (de preferência de longa duração) |
   | `META_API_VERSION` | Versão da Graph API (ex.: `v19.0`) |
   | `IMAGE_HOST_STRATEGY` | `github` (padrão) ou `catbox` |
   | `IMAGE_HOST_REPO_DIR` | Caminho local do clone do repositório de hospedagem (só p/ `github`) |
   | `IMAGE_HOST_GITHUB_REPO` | Repositório `owner/repo` (ex.: `Reherrmann/vera`) |
   | `IMAGE_HOST_BRANCH` | Branch usada para hospedar (padrão `main`) |
   | `IMAGE_HOST_SUBDIR` | Subpasta onde as imagens publicadas são salvas |

   O `.env` **nunca** deve ser commitado — o `.gitignore` deste diretório já
   cobre isso.

3. Se for usar `IMAGE_HOST_STRATEGY=github`, garanta que
   `IMAGE_HOST_REPO_DIR` aponta para um clone local onde você já tem
   permissão de push configurada (SSH ou credencial HTTPS salva) — o script
   roda `git add/commit/push` nesse diretório a cada imagem.

### Token de longa duração

O token gerado pelo Graph API Explorer expira em 1 hora. Para uso
recorrente, troque por um de longa duração:

```bash
curl "https://graph.facebook.com/v19.0/oauth/access_token?grant_type=fb_exchange_token&client_id={APP_ID}&client_secret={APP_SECRET}&fb_exchange_token={TOKEN_ATUAL}"
```

## Uso

Testar a conexão (não publica nada):

```bash
python publish_instagram.py --verify
```

Testar um carrossel sem publicar de fato:

```bash
python publish_instagram.py --images slide1.png slide2.png --caption "Legenda aqui" --dry-run
```

Publicar de verdade:

```bash
python publish_instagram.py --images slide1.png slide2.png --caption "Legenda aqui"
```

- 1 imagem → publica como post de imagem única.
- 2 a 10 imagens → publica como carrossel.
- Mais de 10 → erro (limite da própria API do Instagram).

Forçar a hospedagem via catbox.moe numa chamada específica:

```bash
python publish_instagram.py --images slide1.png --caption "Legenda aqui" --host catbox
```
