![Custom Django Admin](static/images/14_d.png)



<h1 align="center">Custom Django Admin</h1>

<h4 align="center">User Authentication with Custom Admin</h4>

> This package uses the Django default User Authentication that is built into Django, but has a custom Django Admin Dashboard.  When a user changes or resets thair password they are routed through the built-in Djanto Authentication, with Django branded Admin pages.  This package utilizes the Python Jazzmin package to customize the appearance of the Django Dashboard to look like it is part of your website, but without having to code all of the necessary changes to accomplish this.  Typically you would have to create your own URL routes, create custom html templates, and custom views so that the Authentication pages look as if they are part of your website.

> I am not affiliated with jazzmin in any way.  Jazzmin is a well documented and easy-to-use python package for Django.

## Technology Stack:


> ![Django](https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=green)
![Python](https://img.shields.io/badge/Python-FFD43B?style=for-the-badge&logo=python&logoColor=blue)
![GitHub](https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-563D7C?style=for-the-badge&logo=bootstrap&logoColor=white)
![HTML](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![CSS](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white)
![Markdown](https://img.shields.io/badge/Markdown-000000?style=for-the-badge&logo=markdown&logoColor=white)  


___


### Website:
1. Single page website with links
2. User model with built-in authentication
3. Django default URLs with custom views
4. Django Email backend is Gmail
5. Randomly generated Django Secret Key

___


<h1 align="center">Links</h1>

* Working Demo:  https://customadmin-88ab3088a590.herokuapp.com
    * Login:      guest
    * password:   guest12345
* Jazzmin Package:  https://django-jazzmin.readthedocs.io

___


<h1 align="center">Screenshots</h1>

> ![Default Login](static/images/Django_default_login.png)
![Custom Login](static/images/Django_custom_login.png)
![Default Admin](static/images/Django_default_admin_2.png)
![Custom Admin](static/images/Django_custom_admin.png)
![Custom Admin](static/images/Django_custom_admin_user_view.png)
![Custom Password Change](static/images/Django_custom_password_change.png)
![Drones](static/images/Django_custom_password_reset.png)