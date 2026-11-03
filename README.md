# server-app-progeficaz

API Flask para calcular trajetos a pé e gerenciar favoritas por usuário.
Frontend: [app-progeficaz-route-calculator](https://github.com/Luigiverderio/app-progeficaz-route-calculator).

**URL pública da API: pendente de deploy.** Após publicar, substitua esta linha
pelo link real e confirme `GET /health` retornando 200 com o Atlas disponível.

## Configuração

Copie `.env.example` para `.env` e configure `MONGO_URI`, `DB_NAME` e
`JWT_SECRET_KEY`. O segredo JWT deve ser aleatório e privado; a aplicação recusa
iniciar quando ele não está definido ou contém apenas espaços.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Preencha o .env antes de iniciar.
.\.venv\Scripts\python.exe app.py
```

Se o `.env` já existir, mantenha seus valores e acrescente apenas as variáveis
novas. Nunca envie esse arquivo ao Git.

| Variável | Uso |
| --- | --- |
| `MONGO_URI` | URI privada do MongoDB Atlas. |
| `DB_NAME` | Nome do banco da aplicação. |
| `JWT_SECRET_KEY` | Segredo privado e estável usado na assinatura dos tokens. |
| `CORS_ORIGINS` | Origens permitidas, separadas por vírgula; inclua esquema e porta, sem caminho ou barra final. O padrão permite o Vite local na porta 5173. |
| `NOMINATIM_URL` | Endpoint de busca; o padrão usa o serviço público do Nominatim. |

`ORS_API_KEY` não é utilizada: o cálculo usa OSRM e Nominatim sem chave.
Para gerar um segredo JWT, execute `python -c "import secrets; print(secrets.token_hex(32))"`
e coloque o valor no `.env`. Alterar esse segredo invalida os tokens existentes.

A inicialização cria um índice único em `users.email`. Se já houver documentos
com e-mails duplicados, resolva os conflitos antes de iniciar a aplicação; nenhum
documento é removido automaticamente.

As senhas aceitam até 72 bytes em UTF-8, limite do bcrypt. Caracteres acentuados
podem ocupar mais de um byte. Senhas acima do limite retornam HTTP 400 no cadastro
e HTTP 401 no login, com a mesma mensagem de credenciais inválidas.

## Contrato HTTP

Os corpos de POST/PUT usam JSON. Rotas protegidas exigem
`Authorization: Bearer <token>`; tokens ausentes, inválidos ou expirados retornam 401.

| Método e rota | Corpo | Sucesso | Erros principais |
| --- | --- | --- | --- |
| `GET /health` | — | 200: `status` | 503: banco indisponível |
| `POST /auth/register` | `name`, `email`, `password` | 201: `id` | 400, 409: e-mail duplicado, 503 |
| `POST /auth/login` | `email`, `password` | 200: `token`, `name` | 400, 401, 503 |
| `POST /rota` | `origem`, `destino` em texto | 200: `duracao_min`, `distancia_km`, `coordenadas`, `origem`, `destino` | 400, 401, 404: endereço ausente, 502: serviço externo indisponível |
| `POST /favoritas` | `nome`, `origem`, `destino`, `ultima_duracao_min` | 201: `id` | 400, 401, 503 |
| `GET /favoritas` | — | 200: `total`, `favoritas` | 401, 503 |
| `PUT /favoritas/<id>` | `ultima_duracao_min` | 200: favorita atualizada | 400, 401, 404, 503 |
| `DELETE /favoritas/<id>` | — | 204 sem corpo | 401, 404, 503 |

Cada usuário só lista, atualiza ou apaga suas favoritas. IDs inválidos,
inexistentes ou de outro usuário retornam 404. A duração deve ser um número
finito não negativo; PUT altera somente esse campo.

`coordenadas` usa pares `[latitude, longitude]`. `origem` e `destino` na resposta
de `/rota` são objetos `{lat, lng}`. Distância está em km e duração em minutos.
Falhas do MongoDB durante as requisições retornam JSON com status 503.
Se o banco estiver indisponível na inicialização, reinicie o servidor após
corrigir a conexão; a aplicação não recria automaticamente uma conexão ausente.

## Geocodificação

`geocode(endereco)` em `app.py` retorna `(latitude, longitude)` como números ou
`None` quando não encontra o endereço ou ocorre uma falha na consulta.
A função não define respostas HTTP; quem a chama decide a resposta ao usuário.
O endpoint `POST /rota` usa a opção `raise_on_error=True` para responder 502
quando o serviço falha e 404 quando o endereço não é encontrado. Ele exige JWT
e recebe `origem` e `destino` como endereços em texto no JSON.

O serviço pode ser alterado pela variável opcional `NOMINATIM_URL` (URL de busca).
As consultas têm timeout de 5 segundos, identificação via `User-Agent`, cache
de até 128 endereços e intervalo mínimo de 1 segundo por processo.
Ao usar o serviço público, execute apenas um processo/instância para respeitar
o limite total de 1 consulta por segundo da aplicação. Use somente buscas
solicitadas pelo usuário, sem autocomplete ou consultas em massa.
Veja a [política de uso](https://operations.osmfoundation.org/policies/nominatim/)
e a [documentação de busca](https://nominatim.org/release-docs/latest/api/Search/).
Ao exibir os resultados, inclua a atribuição
[© OpenStreetMap contributors](https://www.openstreetmap.org/copyright).

## Preparação para deploy na AWS

Ainda é necessário publicar o backend no EC2 e o frontend React na AWS.
No Linux do servidor, com Python 3.11 ou superior:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# Configure o .env com os dados reais antes do próximo comando.
.venv/bin/gunicorn --config gunicorn.conf.py app:app
```

O Gunicorn não funciona diretamente no Windows; use o comando de desenvolvimento
local ou Linux/WSL. O arquivo `gunicorn.conf.py` mantém um único processo e quatro
threads, preservando o limite compartilhado de consultas ao Nominatim. Não use
`--preload`, múltiplos workers ou múltiplas instâncias com o serviço público.

O Gunicorn escuta em `127.0.0.1:5000`, para receber requisições por um proxy
reverso. Exemplo de configuração Nginx para a API:

```nginx
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 65s;
    }
}
```

Antes de considerar o deploy pronto:

1. Configure `CORS_ORIGINS` com a origem real do React e mantenha o segredo JWT
   estável entre reinicializações.
2. Autorize o acesso do EC2 no Atlas e confira as credenciais e permissões do banco.
3. Configure o processo para iniciar/reiniciar com um gerenciador como systemd.
4. Publique o frontend com `VITE_API_URL` apontando para a API e HTTPS em ambos
   quando o frontend usar HTTPS, evitando bloqueio de conteúdo misto.
5. Confirme cadastro, login, cálculo de rota e CRUD de favoritas pelo navegador,
   incluindo isolamento entre dois usuários e atualização direta de `/mapa`.
6. Adicione as URLs públicas aos READMEs e envie os commits aos repositórios.

O prazo de uma consulta envolve duas geocodificações, o intervalo do Nominatim
e o cálculo do OSRM. O frontend deve permitir 60 segundos para `/rota`; cinco
segundos podem cancelar uma consulta válida. Em filas ou serviços muito lentos,
ainda pode haver timeout. Evite disparar cálculos simultâneos.

## Testes

```powershell
python -m pip install -r requirements.txt
pytest -v
```

Os testes usam uma coleção simulada e não acessam o MongoDB configurado no `.env`.
O `test_app.py`, ao lado de `app.py`, contém o fixture `client` e os testes HTTP
de autenticação, favoritas e `POST /rota`, organizados com comentários Given-When-Then.
O `connect_db` é substituído antes da importação da aplicação, e cada teste
recebe um banco falso com `MagicMock`. Tokens JWT de teste mantêm a autenticação
das rotas protegidas ativa.

Os testes de `POST /rota` simulam `requests.get` com `side_effect`: duas respostas
do Nominatim e uma do OSRM, além dos casos 401, 400, 404 e 502.
O cache da geocodificação é isolado por teste, sem esperas reais entre chamadas.

O `conftest.py` da raiz bloqueia MongoClient, HTTP real, conexões de socket e
resolução DNS desde a coleta dos testes. Qualquer tentativa de acesso externo
gera uma falha; a suíte roda sem Atlas e sem internet. Para repetir a verificação
com o wi-fi desligado, desative a rede e execute o mesmo `pytest -v`.

Para executar apenas os casos de rota ou investigar uma falha:

```powershell
pytest -v -k test_rota
pytest -v -x
pytest -v -s
```

Referências: [side_effect no unittest.mock](https://docs.python.org/3/library/unittest.mock.html#unittest.mock.Mock.side_effect)
e [tokens JWT](https://flask-jwt-extended.readthedocs.io/en/stable/basic_usage.html).
