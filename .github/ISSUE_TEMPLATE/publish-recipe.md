---
name: Publish recipe
about: Publish a recipe to GitHub Pages
title: "Publish recipe: "
labels: publish
---

<!-- SLUG START -->
paste-slug-here
<!-- SLUG END -->

<!-- HTML START -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Recipe Title</title>
</head>
<body>
  <main itemscope itemtype="https://schema.org/Recipe">

    <h1 itemprop="name">Recipe Title</h1>

    <!-- Optional: Include only if present in source -->
    <p><strong>Servings:</strong> <span itemprop="recipeYield">X servings</span></p>

    <h2>Ingredients</h2>
    <ul>
      <li itemprop="recipeIngredient">Ingredient</li>
    </ul>

    <h2>Instructions</h2>
    <ol>
      <li itemprop="recipeInstructions">Step</li>

      <li itemprop="recipeInstructions">Step</li>
    </ol>

  </main>
</body>
</html>
<!-- HTML END -->
