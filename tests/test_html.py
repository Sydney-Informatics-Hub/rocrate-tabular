import sys
import os
from pathlib import Path
import json
import pytest

# Add the parent directory to sys.path so we can import tc-html.py
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the tc-html module (since it has a hyphen, we need to import it this way)
import importlib.util
spec = importlib.util.spec_from_file_location(
    "tc_html", 
    str(Path(__file__).parent.parent / "tc-html.py")
)
tc_html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tc_html)

from tinycrate.tinycrate import TinyCrate, minimal_crate

def test_crate_lite_structure():
    """Test that crate_lite creates the expected structure"""
    # Create a minimal test crate
    crate = minimal_crate()
    # Add a test dataset
    crate.add("Dataset", "#test_dataset", {
        "name": "Test Dataset",
        "description": "A test dataset for testing crate_lite"
    })
    
    # Generate the crate_lite structure
    lite = tc_html.crate_lite(crate)
    
    # Verify the structure
    assert "entryPoint" in lite
    assert "ids" in lite
    assert "types" in lite
    assert lite["entryPoint"] == "./"
    
    # Check if the root entity is present
    assert "./" in lite["ids"]
    assert "#test_dataset" in lite["ids"]
    
    # Check types
    assert "Dataset" in lite["types"]
    assert "#test_dataset" in lite["types"]["Dataset"]
    
    # Check properties
    root = lite["ids"]["./"]
    assert "props" in root
    
    test_dataset = lite["ids"]["#test_dataset"]
    assert "props" in test_dataset
    assert "http://schema.org/name" in test_dataset["props"]
    assert test_dataset["props"]["http://schema.org/name"]["fwd"][0]["value"] == "Test Dataset"

def test_expand_property_value():
    """Test expand_property_value function"""
    crate = minimal_crate()
    crate.add("Dataset", "#test_dataset", {"name": "Test Dataset"})
    
    # Test with a simple string value
    result = tc_html.expand_property_value(crate, "name", "Simple Value")
    assert len(result) == 1
    assert result[0]["value"] == "Simple Value"
    assert not result[0]["target_id"]
    assert not result[0]["url"]
    
    # Test with a reference to another entity
    result = tc_html.expand_property_value(crate, "hasPart", {"@id": "#test_dataset"})
    assert len(result) == 1
    assert result[0]["target_id"] == "#test_dataset"
    assert result[0]["target_name"] == "Test Dataset"

def test_render_template(tmp_path):
    """Test template rendering"""
    # Create a minimal test crate
    crate = minimal_crate()
    # Add a test dataset
    crate.add("Dataset", "#test_dataset", {
        "name": "Test Dataset",
        "description": "A test dataset for testing template rendering"
    })
    
    # Generate the crate_lite structure
    lite = tc_html.crate_lite(crate)
    
    # Create a simple test template
    template_path = tmp_path / "test_template.html"
    with open(template_path, "w") as f:
        # Use a raw string (r prefix) to avoid escape sequence issues
        f.write(r"""
        <html>
        <head><title>Test Template</title></head>
        <body>
            <h1>RO-Crate: {{ data.entryPoint }}</h1>
            <ul>
            {% for id, entity in data.ids.items() %}
                <li>
                    <strong>{{ id }}</strong>: 
                    {% if entity.props["http://schema.org/name"] and entity.props["http://schema.org/name"].fwd %}
                        {{ entity.props["http://schema.org/name"].fwd[0].value }}
                    {% else %}
                        No name
                    {% endif %}
                </li>
            {% endfor %}
            </ul>
        </body>
        </html>
        """)
    
    # Create a simple layout
    layout = [
        {
            "name": "Basic Information",
            "inputs": [
                "http://schema.org/name", 
                "http://schema.org/description"
            ]
        }
    ]
    
    # Render the template
    html = tc_html.render_template(lite, template_path, layout)
    
    # Basic verification
    assert "<h1>RO-Crate: ./</h1>" in html
    assert "<strong>#test_dataset</strong>" in html
    assert "Test Dataset" in html

def test_with_real_crate(crates):
    """Test with a real crate from the test fixtures"""
    cratedir = crates["languageFamily"]
    crate = TinyCrate(Path(cratedir))
    
    # Generate the crate_lite structure
    lite = tc_html.crate_lite(crate)
    
    # Basic verification of the structure
    assert "entryPoint" in lite
    assert "ids" in lite
    assert "types" in lite
    

    
    # Verify we have the expected types
    assert "File" in lite["types"]
    
    # Check the main function with the real crate
    # Create a simple test template with raw strings to avoid escape sequence issues
    template_string = """
        <html>
        <head><title>Test Template</title></head>
        <body>
            <h1>{{ data.entryPoint }}</h1>
            <ul>
            {% for id in data.types.File %}
                <li>{{ id }}</li>
            {% endfor %}
            </ul>
        </body>
        </html>
        """
    
    # Create a simple layout
    layout = [
        {
            "name": "Basic Information",
            "inputs": [
                "http://schema.org/name", 
                "http://schema.org/description"
            ]
        }
    ]
    
    html = tc_html.render_template_string(lite, template_string, layout) 
    
    assert "<h1>UDHR_w_subcollections</h1>" in html
        #assert "<li>doc001/textfile.txt</li>" in html

if __name__ == "__main__":
    # If run directly, execute a simple test
    crate = minimal_crate()
    lite = tc_html.crate_lite(crate)
    print(json.dumps(lite, indent=2))