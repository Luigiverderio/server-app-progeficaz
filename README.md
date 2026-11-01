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
python -m pytest -q
```

Os testes usam uma coleção simulada e não acessam o MongoDB configurado no `.env`.
