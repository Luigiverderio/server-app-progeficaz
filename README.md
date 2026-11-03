# server-app-progeficaz

## Configuração

Copie `.env.example` para `.env` e configure `MONGO_URI`, `DB_NAME` e
`JWT_SECRET_KEY`. O segredo JWT deve ser aleatório e privado; a aplicação recusa
iniciar quando ele não está definido ou contém apenas espaços.

A inicialização cria um índice único em `users.email`. Se já houver documentos
com e-mails duplicados, resolva os conflitos antes de iniciar a aplicação; nenhum
documento é removido automaticamente.

As senhas aceitam até 72 bytes em UTF-8, limite do bcrypt. Caracteres acentuados
podem ocupar mais de um byte. Senhas acima do limite retornam HTTP 400 no cadastro
e HTTP 401 no login, com a mesma mensagem de credenciais inválidas.

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
