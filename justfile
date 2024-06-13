# see https://cheatography.com/linux-china/cheat-sheets/justfile/

set dotenv-load

# Export all just variables as environment variables.
set export

package := "lieelicitationprompts"

[private]
default: @just --list

# put your run commands here
app:
   echo "hello world"

# black and isort
lint:  
   ruff .

