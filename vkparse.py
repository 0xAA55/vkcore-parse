#!/usr/bin/env python3
# -*- coding: utf-8 -*
import io
import os
import json

# The `pushd()` implementation from `https://gist.github.com/howardhamilton/537e13179489d6896dd3`
from contextlib import contextmanager

@contextmanager
def pushd(new_dir):
	previous_dir = os.getcwd()
	if len(new_dir):
		os.chdir(new_dir)
	try:
		yield
	finally:
		os.chdir(previous_dir)

def parse(input, initial = {}, is_include_header = 0):
	ret = initial
	cur_ver = ''
	sharp_if_level = 0
	is_enum = False
	is_union = False
	is_struct = False
	is_proto = False
	is_cpp = False
	is_typedef_func = False
	is_multiline_comment = False
	cur_func = {}
	cur_enum = {}
	cur_union = {}
	cur_struct = {}
	cur_func_name = ''
	cur_enum_name = ''
	cur_union_name = ''
	cur_struct_name = ''
	all_enum = {}
	all_const = {}
	must_alias = {
		'int8_t': 'i8',
		'int16_t': 'i16',
		'int32_t': 'i32',
		'int64_t': 'i64',
		'uint8_t': 'u8',
		'uint16_t': 'u16',
		'uint32_t': 'u32',
		'uint64_t': 'u64',
		'size_t': 'usize',
		'char': 'i8',
		'signed char': 'i8',
		'unsigned char': 'u8',
		'short': 'i16',
		'signed short': 'i16',
		'unsigned short': 'u16',
		'int': 'i32',
		'signed int': 'i32',
		'unsigned': 'u32',
		'unsigned int': 'u32',
		'long': 'i64',
		'signed long': 'i64',
		'unsigned long': 'u64',
		'long long': 'i64',
		'signed long long': 'i64',
		'unsigned long long': 'u64',
		'float': 'f32',
		'double': 'f64',
		'const char*': "&'static str",
	}
	try:
		metadata = ret['metadata']
		all_enum = metadata['all_enum']
		all_const = metadata['all_const']
		must_alias |= metadata['must_alias']
	except KeyError:
		pass
	enabled = False
	if is_include_header:
		enabled = True
	last_line = ''
	with open(input, 'r') as f:
		for line in f:
			if is_multiline_comment:
				if '*/' in line:
					line = line.split('*/', 1)[1].lstrip()
					is_multiline_comment = False
				else:
					continue
			while '/*' in line:
				if '*/' in line:
					left, right = line.split('/*', 1)
					line = left.rstrip() + ' ' + right.split('*/', 1)[1].lstrip()
				else:
					line = line.split('/*', 1)[0].rstrip()
					is_multiline_comment = True
			line = line.split('//', 1)[0].rstrip()
			trimmed_line = line.lstrip()
			indent = len(line) - len(trimmed_line)
			line = (last_line + ' ' + trimmed_line).lstrip()
			last_line = ''
			if line is None or len(line) == 0:
				continue
			if line.endswith('\\'):
				last_line += line[:-1]
				continue
			if line.startswith(('#ifdef ', '#ifndef ')):
				sharp_if_level += 1
				if line.startswith('#ifndef VK_NO_PROTOTYPES'):
					is_proto = True
				elif line.startswith('#ifdef __cplusplus'):
					is_cpp = True
				continue
			if line.startswith("#else"):
				continue
			if line.startswith('#endif'):
				sharp_if_level -= 1
				if sharp_if_level <= 1:
					is_proto = False
					is_cpp = False
				continue
			if line.startswith('#include'):
				print('\t' * is_include_header + line)
				if '<' in line or '>' in line:
					continue
				include_file = line.split('"', 2)[1]
				include_path = os.path.dirname(include_file)
				include_file = os.path.basename(include_file)
				if include_file == 'vk_platform.h':
					print('\t' * is_include_header + 'Skipped: "vk_platform.h"')
					continue
				with pushd(include_path):
					ret['metadata'] = {
						'all_enum': all_enum,
						'all_const': all_const,
						'must_alias': must_alias,
					}
					parsed = parse(include_file, ret, is_include_header + 1)
					metadata = parsed['metadata'].copy()
					del parsed['metadata']
					ret |= parsed
					all_enum |= metadata['all_enum']
					all_const |= metadata['all_const']
					must_alias |= metadata['must_alias']
				continue
			if enabled == False:
				if line.startswith('#define VK_VERSION_1_0 1'):
					enabled = True
				else:
					continue
			if 'VK_MAKE_' in line and '_VERSION' in line:
				continue
			if line.startswith(('#define VK_', '#define vulkan_')) and line.endswith(' 1') and indent == 0 and line.endswith('_SPEC_VERSION') == False:
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
				if cur_ver == 'VK_VERSION_1_0':
					for type, alias in must_alias.items():
						if ' ' not in type and '*' not in type:
							ret[cur_ver]['typedefs'][type] = alias
			if is_cpp:
				print('\t' * is_include_header + f'Skip cpp code: {line}')
				continue
			if line.startswith('#define ') and line.endswith('_H_ 1'):
				print('\t' * is_include_header + line)
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
					cur_enum |= {name.strip(): value.strip()}
					all_enum |= {name.strip(): [value.strip(), cur_enum_name]}
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
	ret['metadata'] = {'all_enum': all_enum}
	return ret

def to_rust(outfile, parsed):
	all_enum = parsed['metadata']['all_enum']
	with open(outfile, 'w') as f:
		f.write('\n')
		f.write('#![allow(dead_code)]\n')
		f.write('#![allow(non_camel_case_types)]\n')
		f.write('\n')
		f.write('use std::{\n')
		f.write('\tffi::c_void,\n')
		f.write('};\n')
		f.write('\n')
		f.write('type int8_t  = i8;\n')
		f.write('type int16_t = i16;\n')
		f.write('type int32_t = i32;\n')
		f.write('type int64_t = i64;\n')
		f.write('type uint8_t  = u8;\n')
		f.write('type uint16_t = u16;\n')
		f.write('type uint32_t = u32;\n')
		f.write('type uint64_t = u64;\n')
		for version, verdata in parsed.items():
			if version == 'metadata':
				continue
			for type, tname in verdata['typedefs'].items():
				if tname == 'void*':
					tname = 'c_void'
				f.write(f'type {type} = {tname};\n')
			for handle in verdata['handles']:
				f.write(f'// Define handle `{handle}`\n')
				f.write(f'#[derive(Debug, Clone, Copy)] pub struct {handle}_T {{}}\n')
				f.write(f'type {handle} = *const {handle}_T;\n')
			for handle in verdata['non_dispatchable_handles']:
				f.write(f'// Define non-dispatchable handle `{handle}`\n')
				f.write(f'#[cfg(target_pointer_width = "32")] type {handle} = u64;\n')
				f.write(f'#[cfg(target_pointer_width = "64")] #[derive(Debug, Clone, Copy)] pub struct {handle}_T {{}}\n')
				f.write(f'#[cfg(target_pointer_width = "64")] type {handle} = *const {handle}_T;\n')
			for enum, enumpair in verdata['enums'].items():
				asso = io.StringIO()
				f.write(f'pub enum {enum} {{\n')
				for enumname, enumval in enumpair.items():
					try:
						enumdef, enumfrom = all_enum[enumval]
						asso.write(f'\tpub const {enumname}: {enumfrom} = {enumfrom}::{enumval};\n')
					except KeyError:
						enumval = enumval.lower()
						if enumval.endswith('ull'): enumval = f'{enumval[:-3]}u64'
						if enumval.endswith('ll'): enumval = f'{enumval[:-2]}i64'
						if enumval.endswith('u'): enumval = f'{enumval[:-1]}u32'
						if enumval.endswith('l'): enumval = f'{enumval[:-1]}i32'
						if enumval.endswith('f') and '.' in enumval: enumval = f'{enumval[:-1]}f32'
						if enumval[0] == '~': enumval = f'!{enumval[1:]}'
						f.write(f'\t{enumname} = {enumval},\n')
				f.write('}\n')
				asso = asso.getvalue()
				if len(asso):
					f.write(f'impl {enum} {{\n')
					f.write(asso)
					f.write('}\n')
				asso = None

if __name__ == '__main__':
	parsed = parse('vulkan_core.h')
	with open('vkcore.json', 'w') as f:
		json.dump(parsed, f, indent=4)
	to_rust('vkcore.rs', parsed)
