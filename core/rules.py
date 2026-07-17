import json
import re
from typing import List, Optional
from .models import db, UserPreference

class Rule:
    def __init__(self, rule_id: int, field: str, operator: str, value: str, label: str):
        self.rule_id = rule_id
        self.field = field          # one of: 'sender', 'subject', 'snippet'
        self.operator = operator    # one of: 'contains', 'equals', 'starts_with', 'ends_with', 'regex'
        self.value = value
        self.label = label
        self._regex = None
        if operator == 'regex':
            try:
                self._regex = re.compile(value, re.IGNORECASE)
            except re.error:
                self._regex = None

    def matches(self, text: str) -> bool:
        if not isinstance(text, str):
            text = str(text or '')
        if self.operator == 'contains':
            return self.value.lower() in text.lower()
        elif self.operator == 'equals':
            return self.value.lower() == text.lower()
        elif self.operator == 'starts_with':
            return text.lower().startswith(self.value.lower())
        elif self.operator == 'ends_with':
            return text.lower().endswith(self.value.lower())
        elif self.operator == 'regex':
            if self._regex:
                return bool(self._regex.search(text))
            else:
                return False
        else:
            return False

    def to_dict(self):
        return {
            'field': self.field,
            'operator': self.operator,
            'value': self.value,
            'label': self.label
        }

    @staticmethod
    def from_dict(data: dict, rule_id: int = None):
        return Rule(
            rule_id=rule_id if rule_id is not None else data.get('id', 0),
            field=data['field'],
            operator=data['operator'],
            value=data['value'],
            label=data['label']
        )

class RuleManager:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.rules: List[Rule] = []
        self._load_rules()

    def _load_rules(self):
        prefs = db.session.query(UserPreference).filter_by(user_id=self.user_id).all()
        self.rules = []
        for pref in prefs:
            if pref.key.startswith('rule_'):
                try:
                    data = json.loads(pref.value)
                    rule_num = int(pref.key.split('_')[1])
                    rule = Rule.from_dict(data, rule_id=rule_num)
                    self.rules.append(rule)
                except (json.JSONDecodeError, ValueError, KeyError):
                    continue
        self.rules.sort(key=lambda r: r.rule_id)

    def add_rule(self, field: str, operator: str, value: str, label: str) -> int:
        existing_ids = [r.rule_id for r in self.rules]
        new_id = max(existing_ids) + 1 if existing_ids else 1
        rule = Rule(new_id, field, operator, value, label)
        self.rules.append(rule)
        pref = UserPreference(
            user_id=self.user_id,
            key=f'rule_{new_id}',
            value=json.dumps(rule.to_dict())
        )
        db.session.add(pref)
        db.session.commit()
        return new_id

    def remove_rule(self, rule_id: int) -> bool:
        for i, r in enumerate(self.rules):
            if r.rule_id == rule_id:
                del self.rules[i]
                pref = db.session.query(UserPreference).filter_by(user_id=self.user_id, key=f'rule_{rule_id}').first()
                if pref:
                    db.session.delete(pref)
                    db.session.commit()
                return True
        return False

    def update_rule(self, rule_id: int, field: str, operator: str, value: str, label: str) -> bool:
        for r in self.rules:
            if r.rule_id == rule_id:
                r.field = field
                r.operator = operator
                r.value = value
                r.label = label
                pref = db.session.query(UserPreference).filter_by(user_id=self.user_id, key=f'rule_{rule_id}').first()
                if pref:
                    pref.value = json.dumps(rule.to_dict())
                    db.session.commit()
                return True
        return False

    def get_rules(self) -> list:
        return [r.to_dict() for r in self.rules]

    def predict_label(self, email_dict: dict) -> Optional[str]:
        for rule in self.rules:
            text = email_dict.get(rule.field, '')
            if rule.matches(text):
                return rule.label
        return None

    def parse_command(self, cmd: str) -> str:
        cmd = cmd.strip()
        if not cmd:
            return "Ingrese un comando. Escriba 'help' para ver la lista de comandos."
        parts = cmd.split()
        if not parts:
            return "Comando no reconocido."
        cmd_lower = parts[0].lower()
        if cmd_lower == 'help':
            return (
                "Comandos disponibles:\n"
                "  help                           - muestra esta ayuda\n"
                "  list rules                     - lista todas las reglas\n"
                "  add rule <field> <operator> \"<value>\" as \"<label>\"\n"
                "                                 - ejemplo: add rule subject contains \"factura\" as \"Facturas\"\n"
                "  remove rule <id>               - elimina la regla con el ID dado\n"
                "  update rule <id> <field> <operator> \"<value>\" as \"<label>\""
            )
        elif len(parts) >= 2 and parts[0].lower() == 'list' and parts[1].lower() == 'rules':
            if not self.rules:
                return "No hay reglas definidas."
            lines = ["Reglas actuales:"]
            for r in self.rules:
                lines.append(f"  ID {r.rule_id}: {r.field} {r.operator} \"{r.value}\" -> {r.label}")
            return "\n".join(lines)
        elif parts[0].lower() == 'add' and len(parts) >= 6 and parts[1].lower() == 'rule':
            # parse: add rule <field> <operator> "<value>" as "<label>"
            try:
                # Reconstruct the part after 'add rule'
                rest = ' '.join(parts[2:])
                if '" as "' not in rest:
                    return "Formato incorrecto. Use: add rule <field> <operator> \"<value>\" as \"<label>\""
                left, right = split_first(rest, '" as "')
                label = right.rstrip('"')
                tokens = left.split()
                if len(tokens) < 3:
                    return "Formato incorrecto. Falta campo, operador o valor."
                field = tokens[0]
                operator = tokens[1]
                value_part = ' '.join(tokens[2:])
                if not (value_part.startswith('"') and value_part.endswith('"')):
                    return "El valor debe estar entre comillas dobles."
                value = value_part[1:-1]
                if field not in ('sender', 'subject', 'snippet'):
                    return "Campo no válido. Use: sender, subject o snippet."
                if operator not in ('contains', 'equals', 'starts_with', 'ends_with', 'regex'):
                    return "Operador no válido. Use: contains, equals, starts_with, ends_with, regex."
                rid = self.add_rule(field, operator, value, label)
                return f"Regla agregada con ID {rid}."
            except Exception as e:
                return f"Error al agregar regla: {e}"
        elif parts[0].lower() == 'remove' and len(parts) >= 3 and parts[1].lower() == 'rule':
            try:
                rid = int(parts[2])
                if self.remove_rule(rid):
                    return f"Regla {rid} eliminada."
                else:
                    return f"No se encontró la regla con ID {rid}."
            except ValueError:
                return "ID de regla debe ser un número entero."
        elif parts[0].lower() == 'update' and len(parts) >= 6 and parts[1].lower() == 'rule':
            # update rule <id> <field> <operator> "<value>" as "<label>"
            try:
                rid = int(parts[2])
                rest = ' '.join(parts[3:])
                if '" as "' not in rest:
                    return "Formato incorrecto. Use: update rule <id> <field> <operator> \"<value>\" as \"<label>\""
                left, right = split_first(rest, '" as "')
                label = right.rstrip('"')
                tokens = left.split()
                if len(tokens) < 3:
                    return "Formato incorrecto. Falta campo, operador o valor."
                field = tokens[0]
                operator = tokens[1]
                value_part = ' '.join(tokens[2:])
                if not (value_part.startswith('"') and value_part.endswith('"')):
                    return "El valor debe estar entre comillas dobles."
                value = value_part[1:-1]
                if field not in ('sender', 'subject', 'snippet'):
                    return "Campo no válido. Use: sender, subject o snippet."
                if operator not in ('contains', 'equals', 'starts_with', 'ends_with', 'regex'):
                    return "Operador no válido. Use: contains, equals, starts_with, ends_with, regex."
                if self.update_rule(rid, field, operator, value, label):
                    return f"Regla {rid} actualizada."
                else:
                    return f"No se encontró la regla con ID {rid}."
            except ValueError:
                return "ID de regla debe ser un número entero."
        else:
            return "Comando no reconocido. Escriba 'help' para ver los comandos disponibles."

def split_first(s: str, delim: str):
    """Split string on first occurrence of delim, return (left, right)."""
    idx = s.find(delim)
    if idx == -1:
        return s, ''
    return s[:idx], s[idx+len(delim):]