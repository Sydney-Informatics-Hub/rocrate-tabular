from tinycrate.tinycrate import TinyCrate, TinyCrateException, minimal_crate
from argparse import ArgumentParser
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import os
import re

def as_array(value):
    """
    Convert a value to an array if it is not already one.
    If the value is None, return an empty array.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

def initialize_prop(crate, entity_lite, prop):
    """
    Initialize a property in the entity_lite dictionary.
    If the property is a URL, resolve it using the crate's context.
    If the property is a list, convert it to an array.
    
    Args:
        crate: The TinyCrate instance
        entity_lite: The entity_lite dictionary to update
        prop: The property name to initialize
        
    Returns:
        The resolved URI for the property
    """
    print(f"Initializing property '{prop}'")
    uri = crate.resolve_term(prop)
    print(f"Resolved property '{prop}' to URI '{uri}'")
    # Initialize the property if it doesn't exist
    if uri not in entity_lite["props"]:
        entity_lite["props"][uri] = {
            "fwd": [],
            "rev": [],
            "label": prop,
        }
    
    # Set the URL based on whether the URI is the same as the property
    # or if it's an entity in the crate
    if uri == prop:
        entity_lite["props"][uri]["url"] = None
    elif crate.get(uri):
        entity_lite["props"][uri]["url"] = f"#{uri}"
    else:
        entity_lite["props"][uri]["url"] = uri
    
    return uri

def expand_property_value(crate, property, value):
    """
    Expand a property value to include metadata about the value.
    
    Args:
        crate: The TinyCrate instance
        property: The property name
        value: The property value to expand
        
    Returns:
        List of expanded values with metadata
    """
    print("Here in expand_property_value")
    vals = []
    
    # Handle special properties
    if property == "@id" or property == "@value":
        return value
    
    # Process each value in the array
    for val in as_array(value):
        print(f"Expanding property '{property}' with value: {val}")
        return_val = {
            "value": "",
            "target_id": "",
            "target_name": "",
            "url": "",
        }
        
        if isinstance(val, dict) and "@id" in val:
            # Skip the metadata file
            if val["@id"] == "ro-crate-metadata.json":
                continue
                
            target = crate.get(val["@id"])  # Changed from get_entity to get
            if target:
                print(f"Found target for value '{val}' with ID '{val['@id']}'")
                return_val["target_id"] = val["@id"]
                # Get name from target or use ID if no name
                if target["name"]:
                    name = ", ".join(as_array(target["name"]))
                else:
                    name = val["@id"]
                return_val["target_name"] = name
            else:
                # Check if it's a URL
                try:
                    # Just trying to validate if it's a URL
                    from urllib.parse import urlparse
                    result = urlparse(val["@id"])
                    if all([result.scheme, result.netloc]):
                        return_val["url"] = val["@id"]
                except:
                    return_val["value"] = val
        else:
            # Simple value
            return_val["value"] = val
        
        # Only add to results if it has a value, target_id, or url
        if return_val["value"] or return_val["target_id"] or return_val["url"]:
            vals.append(return_val)
    
    return vals

def crate_lite(crate):
    """
    Build a flattened data structure from the RO-Crate the same as the one in ro-crate-html-lite.js

    """
    root = crate.root()
    crate_lite = { "entryPoint": root.id, "ids": {}, "types": {}, "typeUrls": {} }

   
    for entity in crate.all():
        id = entity.id
        entity_lite = { "id": id, "type": as_array(entity["@type"]), "props": {}};
        for type in as_array(entity["@type"]):
            if type not in crate_lite["types"]:
                crate_lite["types"][type] = []
            crate_lite["types"][type].append(entity["@id"])
        for prop, value in entity.items():
            print(f"Processing property '{prop}' for entity '{id}'")
            if prop == "@id" or prop == "@type":
                continue
            uri = initialize_prop(crate, entity_lite, prop)

            entity_lite["props"][uri]["fwd"] = expand_property_value(crate, prop, entity[prop])  
        crate_lite["ids"][id] = entity_lite
    
    # Now add reverse properties
    for entity in crate.all():
        id = entity.id
        for prop, value in entity.items():
            if prop == "@id" or prop == "@type":
                continue
            uri = crate.resolve_term(prop)

            for val in as_array(value):
                if isinstance(val, dict) and "@id" in val:
                    target_id = val["@id"]
                    if target_id in crate_lite["ids"]:
                        if not uri in crate_lite["ids"][target_id]["props"]:
                            crate_lite["ids"][target_id]["props"][uri] = {
                                "fwd": [],
                                "rev": [],
                                "label": prop,
                                "url": None
                            }
                        crate_lite["ids"][target_id]["props"][uri]["rev"]=  expand_property_value(crate, prop, entity[prop])
              
    
    return crate_lite
       


def parse_args(arg_list=None):
    ap = ArgumentParser("RO-Crate HTML Preview")
    ap.add_argument(
        "crate",
        type=str,
        help="Input RO-Crate URL or directory",
    )
   
    return ap.parse_args(arg_list)

def render_template(data, template_path, layout=None):
    """
    Render a template with the given data and layout.
    
    Args:
        data: The data to render in the template.
        template_path: The path to the Jinja2 template file.
        layout: Optional layout to use for rendering.
        
    Returns:
        Rendered HTML string.
    """
    # load template string from file using standard python file I/O

    template_string =  open(template_path, "r", encoding="utf-8").read()
    
    return render_template_string(data, template_string, layout)
    
def render_template_string(data, template_string, layout=None):
    """
    Render a template string with the given data and layout.
    
    Args:
        data: The data to render in the template.
        template_string: The template string to render.
        layout: Optional layout to use for rendering.
        
    Returns:
        Rendered HTML string.
    """
    import traceback
    from jinja2 import Environment, TemplateSyntaxError
    import json
    import os
    
    # Setup Jinja2 environment for string template
    env = Environment(autoescape=True)
    
    # Add custom filters
    def set_prop(obj, key):
        obj[key] = True
        return obj
    
    def replace_regex(value, pattern, replacement=''):
        try:
            return re.sub(pattern, replacement, str(value))
        except Exception as e:
            print(f"Error in replace_regex filter: {e}")
            return value
    
    def test_regex(value, pattern):
        try:
            return bool(re.search(pattern, str(value)))
        except Exception as e:
            print(f"Error in test_regex filter: {e}")
            return False
    
    def safe_unpack(value, default=""):
        if isinstance(value, (list, tuple)):
            if len(value) >= 2:
                return value[0], value[1]
            elif len(value) == 1:
                return value[0], default
        return value, default
    
    def safe_get(obj, key, default=""):
        try:
            if isinstance(obj, dict):
                if key in obj:
                    return obj[key]
                if key.startswith("http://schema.org/"):
                    short_key = key.split("/")[-1]
                    if short_key in obj:
                        return obj[short_key]
            return default
        except Exception as e:
            print(f"Error in safe_get filter: {e}")
            return default
    
    # Register all filters
    env.filters['setProp'] = set_prop
    env.filters['replace_regex'] = replace_regex
    env.filters['test_regex'] = test_regex
    env.filters['safe_unpack'] = safe_unpack
    env.filters['safe_get'] = safe_get
    
    # Create debug dump if needed
    debug_data_path = os.path.join(os.getcwd(), "debug_data.json")
    try:
        with open(debug_data_path, 'w') as f:
            json.dump({"data": data, "layout": layout}, f, indent=2, default=str)
        print(f"Saved data structure to {debug_data_path} for debugging")
    except Exception as e:
        print(f"Error saving debug data: {e}")
    
    # Create template from string
    template = env.from_string(template_string)
    
    # Render with context
    context = {
        'data': data,
        'layout': layout
    }
    
    try:
        return template.render(**context)
    except Exception as e:
        tb = traceback.format_exc()
        line_number = None
        
        # Extract line number for syntax errors
        if isinstance(e, TemplateSyntaxError):
            line_number = e.lineno
            
            # Show template context around the error
            lines = template_string.split("\n")
            start_line = max(0, line_number - 5)
            end_line = min(len(lines), line_number + 5)
            
            error_context = "Template context:\n"
            for i in range(start_line, end_line):
                prefix = ">> " if i + 1 == line_number else "   "
                error_context += f"{prefix}{i+1}: {lines[i]}\n"
        else:
            error_context = "Could not determine error location in template string"
        
        print(f"Error rendering template: {e}")
        print(error_context)
        print(tb)
        
        # Return error page
        return f"""
        <html>
        <head><title>Error Rendering Template</title></head>
        <body>
            <h1>Error Rendering Template</h1>
            <p>{str(e)}</p>
            <h2>Error Location</h2>
            <p>Line: {line_number if line_number else 'Unknown'}</p>
            <pre>{error_context}</pre>
            <h2>Error Details</h2>
            <pre>{tb}</pre>
        </body>
        </html>
        """

def main(args):
    crate = TinyCrate(args.crate)
    data = crate_lite(crate)
    
    # Fetch the default layout from GitHub
    import requests
    import json
    
    default_url = "https://raw.githubusercontent.com/Language-Research-Technology/crate-o/refs/heads/main/src/lib/components/default_layout.json"
    print(f"Fetching default layout from {default_url}")
    
    try:
        response = requests.get(default_url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        layout = response.json()
        
        # Combine the crate data with the layout into a single object for the template
        template_data = data  # Just pass the crate data
        
        # Render the template
        template_path = os.path.join(os.path.dirname(__file__), "template.html")
        print(f"Rendering template at {template_path}")
        
        rendered_html = render_template(template_data, template_path, layout)
        
        # Save the rendered HTML
        output_path = Path(args.crate, "ro-crate-preview.html")
        with open(output_path, 'w') as f:
            f.write(rendered_html)
        
        print(f"HTML preview saved to {output_path}")
        
        return output_path
    except requests.exceptions.RequestException as e:
        print(f"Error fetching default layout: {e}")
        # Continue with just the crate data if layout fetch fails
        print(json.dumps(data, indent=2))
        return data

def cli():
    args = parse_args()
    main(args)


if __name__ == "__main__":
    cli()
