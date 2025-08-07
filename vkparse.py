#!/usr/bin/env python3
# -*- coding: utf-8 -*
import io
import json

def parse(input):
	ret = {}
	cur_ver = ''
	sharp_if_level = 0
	is_enum = False
	is_union = False
	is_struct = False
	is_proto = False
	is_typedef_func = False
	cur_func = {}
	cur_enum = {}
	cur_union = {}
	cur_struct = {}
	cur_func_name = ''
	cur_enum_name = ''
	cur_union_name = ''
	cur_struct_name = ''
	all_enum = {}
	enabled = False
	with open(input, 'r') as f:
		for line in f:
			line = line.split('//', 1)[0].rstrip()
			lline = line.lstrip()
			indent = len(line) - len(lline)
			line = lline
			if line is None or len(line) == 0:
				continue
			if line.startswith(('#ifdef ', '#ifndef ')):
				sharp_if_level += 1
				if line.startswith('#ifndef VK_NO_PROTOTYPES'):
					is_proto = True
				continue
			if enabled == False:
				if line.startswith('#define VK_VERSION_1_0 1'):
					enabled = True
				else:
					continue
			if 'VK_MAKE_API_VERSION' in line:
				continue
			if line.startswith('#include'):
				continue
			if line.startswith('#define VK_') and line.endswith(' 1') and indent == 0 and 'SPEC_VERSION' not in line:
				cur_ver = line.split(' ', 2)[1];
				ret[cur_ver] = {
					'typedefs': {},
					'handles': [],
					'non_dispatchable_handles': [],
					'constants': {},
					'enums': {},
					'unions': {},
					'structs': {},
					'funcs': [],
					'func_protos': {},
				}
			if line.startswith("#else"):
				continue
			if line.startswith('#endif'):
				sharp_if_level -= 1
				if sharp_if_level <= 1:
					is_proto = False
				continue
			if cur_ver == '':
				print(f'Unversioned line: {line}')
				continue
			if line.startswith('#define '):
				parts = line.split(' ', 2)
				ident, value = parts[1], parts[2].strip()
				if '(' in ident or ')' in ident:
					print(f'Skipped #define {ident} {value}')
					continue
				while f'{value[0]}{value[-1]}' == '()':
					value = value[1:-1]
				if ident != cur_ver:
					ret[cur_ver]['constants'][ident] = value
				continue
			if is_enum:
				if line.startswith('}'):
					is_enum = False
					ret[cur_ver]['enums'][cur_enum_name] = cur_enum
					cur_enum = {}
					continue
				if '=' in line:
					if line.endswith(','):
						line = line[:-1]
					name, value = line.split('=', 1)
					new_enum = {name.strip(): value.strip()}
					cur_enum |= new_enum
					all_enum |= new_enum
				else:
					print(f'Unknown data in enum: "{line}"')
				continue
			elif is_union:
				if line.startswith('}'):
					is_union = False
					ret[cur_ver]['unions'][cur_union_name] = cur_union
					cur_union = {}
					continue
				if line.endswith(';'):
					line = line[:-1]
					type, name = line.rsplit(' ', 1)
					cur_union |= {name.strip(): type.strip()}
				else:
					print(f'Unknown data in union: "{line}"')
				continue
			elif is_struct:
				if line.startswith('}'):
					is_struct = False
					ret[cur_ver]['structs'][cur_struct_name] = cur_struct
					cur_struct = {}
					continue
				if line.endswith(';'):
					line = line[:-1]
					type, name = line.rsplit(' ', 1)
					cur_struct |= {name.strip(): type.strip()}
				else:
					print(f'Unknown data in struct: "{line}"')
				continue
			elif is_proto:
				if line.startswith('VKAPI_ATTR '):
					if line.endswith('('):
						ret[cur_ver]['funcs'] += [line[:-1].rsplit(' ', 1)[-1]]
					else:
						print(f'Unknown data in function declaration: "{line}"')
				continue
			elif is_typedef_func:
				if line.endswith(');'):
					is_typedef_func = False
					line = line[:-2]
				elif line.endswith(','):
					line = line[:-1]
				param_type, param_name = line.rsplit(' ', 1)
				cur_func['params'] |= {param_name.strip(): param_type.strip()}
				if is_typedef_func == False:
					ret[cur_ver]['func_protos'][cur_func_name] = cur_func.copy()
					cur_func = {}
			else:
				if line.startswith('typedef enum '):
					is_enum = True
					cur_enum_name = line[len('typedef enum '):].split(' ', 1)[0]
					cur_enum = {}
					continue
				if line.startswith('typedef union '):
					is_union = True
					cur_union_name = line[len('typedef union '):].split(' ', 1)[0]
					cur_union = {}
					continue
				if line.startswith('typedef struct '):
					is_struct = True
					cur_struct_name = line[len('typedef struct '):].split(' ', 1)[0]
					cur_struct = {}
					continue
				if line.startswith('typedef '):
					if 'VKAPI_PTR' in line:
						cur_func_name = line.split('VKAPI_PTR *', 1)[1].split(')', 1)[0]
						if line.endswith('('):
							is_typedef_func = True
							params = {}
						elif line.endswith(');'):
							params = {}
							for param in line.split(f'{cur_func_name})(', 1)[1].rsplit(')', 1)[0].split(','):
								if param == 'void':
									pass
								elif ' ' in param:
									type, name = param.rsplit(' ', 1)
									params |= {name.strip(): type.strip()}
								else:
									params |= {f'_param_{params.len()}': type.strip()}
						else:
							print(f'Unknown data in function prototype: "{line}"')
							continue
						cur_func = {
							'ret_type': line[len('typedef '):].split('(', 1)[0].strip(),
							'params': params,
						}
						if is_typedef_func == False:
							ret[cur_ver]['func_protos'][cur_func_name] = cur_func.copy()
							cur_func = {}
					else:
						if line.endswith(';'):
							line = line[:-1]
							type, name = line[len('typedef '):].rsplit(' ', 1)
							ret[cur_ver]['typedefs'] |= {name: type}
						else:
							print(f'Unknown data in typedef: "{line}"')
					continue
				if line.startswith('VK_DEFINE_HANDLE'):
					handle_name = line.split('(', 1)[1].split(')', 1)[0]
					ret[cur_ver]['handles'] += [handle_name]
					continue
				if line.startswith('VK_DEFINE_NON_DISPATCHABLE_HANDLE'):
					handle_name = line.split('(', 1)[1].split(')', 1)[0]
					ret[cur_ver]['non_dispatchable_handles'] += [handle_name]
					continue
	for ver_name, ver_data in ret.items():
		for enum, defines in ver_data['enums'].items():
			to_redirect = {}
			for name, value in defines.items():
				if value in all_enum:
					to_redirect[name] = all_enum[value]
			for name, value in to_redirect.items():
				ret[ver_name]['enums'][enum][name] = value
	return ret
			


if __name__ == '__main__':
	parsed = parse('vulkan_core.h')
	with open('vkcore.json', 'w') as f:
		json.dump(parsed, f, indent=4)
